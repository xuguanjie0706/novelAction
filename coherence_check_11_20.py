#!/usr/bin/env python3
"""
通用跨章连贯性评测 CLI（原 11–20 章脚本演进版）
================================================
- 评测维度由「同目录 coherence_check_config.json」配置（可复制后改 items）
- 支持 --project-id / --project-title / 默认最新项目；--list-projects 列出候选
- 章节范围：--from / --to；可选 --config / --output / --skip-followup

用法:
  python coherence_check_11_20.py --list-projects
  python coherence_check_11_20.py --project-id <uuid> --from 1 --to 10
  python coherence_check_11_20.py --config ./my_coherence.json --from 11 --to 20

依赖:
  pip install psycopg2-binary openai python-dotenv httpx
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from copy import deepcopy
from typing import Any, Optional

# ── 加载 .env ──────────────────────────────────────────────────
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "apps/backend/.env"))
except ImportError:
    pass

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None  # type: ignore[assignment]

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]


def _require_psycopg2():
    if psycopg2 is None:
        sys.exit("缺少依赖：pip install psycopg2-binary")


def _require_openai():
    if openai is None:
        sys.exit("缺少依赖：pip install openai")


# ── 环境模型配置（无模型时在 main 中退出，便于 --help）──────────
DB_URL = os.environ.get("DATABASE_URL", "postgresql://novel:novel@localhost:5432/novel_db")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "ollama")
AI_MODEL = os.environ.get("AI_MODEL", "")

GEMINI_BASE_URL = os.environ.get("GEMINI_BASE_URL", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "")

USE_GEMINI = bool(GEMINI_BASE_URL and GEMINI_MODEL)
BASE_URL = GEMINI_BASE_URL if USE_GEMINI else LLM_BASE_URL
API_KEY = GEMINI_API_KEY if USE_GEMINI else LLM_API_KEY
MODEL = GEMINI_MODEL if USE_GEMINI else AI_MODEL
LARGE_CONTEXT = USE_GEMINI

# ── 默认运行配置（与 coherence_check_config.json 结构一致）──────

def _default_run_config() -> dict[str, Any]:
    return {
        "prompts": {
            "main_system_base": (
                "你是资深网文编辑，专门执行跨章连贯性审查。"
                "严格返回 JSON，不要任何额外文字。"
            ),
            "boundary_system": "你是专注于章节衔接的网文审稿编辑。只返回JSON。",
        },
        "context": {
            "include_power_systems": True,
            "include_characters": True,
            "include_storylines": True,
            "include_chapter_indexes": True,
            "character_limit": 20,
            "storyline_limit": 10,
        },
        "sampling": {
            "head_chars": 500,
            "tail_chars": 600,
            "head_chars_large_context": 600,
            "tail_chars_large_context": 700,
            "boundary_snippet_tail": 400,
            "boundary_snippet_head": 400,
            "boundary_deep_tail": 800,
            "boundary_deep_head": 800,
        },
        "evaluation_items": [
            {
                "id": "continuity_gap",
                "title": "场景断层",
                "instruction": (
                    "前章末尾的场景/冲突，在后章开头是否有合理承接或交代？"
                ),
                "include_in_boundary_prompt": True,
            },
            {
                "id": "realm_jump",
                "title": "境界跳跃",
                "instruction": (
                    "对照境界体系等级表，检查每章内及章节间的境界描述，"
                    "是否存在无突破过程的跨级跳变？"
                ),
                "include_in_boundary_prompt": True,
            },
            {
                "id": "character_swap",
                "title": "人物替换/消失",
                "instruction": (
                    "同一场景或连续叙事中，是否存在角色在相邻章节间无故换人"
                    "（姓名变更）或无故消失？"
                ),
                "include_in_boundary_prompt": True,
            },
            {
                "id": "causality_missing",
                "title": "因果缺失",
                "instruction": "前章埋下的冲突（章末钩子），后章是否给出了结果或承接？",
                "include_in_boundary_prompt": True,
            },
            {
                "id": "title_match",
                "title": "标题-正文匹配",
                "instruction": "各章标题与正文核心事件是否匹配？",
                "include_in_boundary_prompt": False,
            },
        ],
        "followup": {
            "enabled": True,
            "always_first_n_boundaries": 3,
            "severity_triggers": ["high", "critical"],
            "risk_level_triggers": ["high"],
        },
        "output": {
            "report_filename_template": "coherence_report_{project_slug}_ch{chapter_from}_{chapter_to}.json",
        },
    }


def deep_merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def load_run_config(path: Optional[str]) -> dict[str, Any]:
    cfg = _default_run_config()
    candidates = []
    if path:
        candidates.append(os.path.abspath(path))
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(here, "coherence_check_config.json"))
    for p in candidates:
        if p and os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                file_cfg = json.load(f)
            cfg = deep_merge(cfg, file_cfg)
            cfg["_loaded_from"] = p
            return cfg
    cfg["_loaded_from"] = None
    return cfg


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def head_tail(text: str, head: int, tail: int) -> str:
    clean = strip_html(text)
    if len(clean) <= head + tail:
        return clean
    return clean[:head] + "\n…（中间省略）…\n" + clean[-tail:]


def tail_only(text: str, n: int) -> str:
    return strip_html(text)[-n:]


def head_only(text: str, n: int) -> str:
    return strip_html(text)[:n]


def parse_json_response(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if m:
            text = m.group(1).strip()
    start = text.find("{")
    if start != -1:
        text = text[start:]
    return json.loads(text)


def project_slug(title: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", (title or "project").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s[:48] or "project").lower()


def get_db_conn():
    _require_psycopg2()
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def list_projects(conn, limit: int = 40) -> list:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, genre, created_at FROM projects "
            "ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        return cur.fetchall()


def fetch_project(
    conn,
    project_id: Optional[str] = None,
    project_title: Optional[str] = None,
) -> Optional[dict]:
    with conn.cursor() as cur:
        if project_id:
            cur.execute(
                "SELECT id, title, premise, genre FROM projects WHERE id = %s",
                (project_id,),
            )
        elif project_title:
            cur.execute(
                "SELECT id, title, premise, genre FROM projects WHERE title ILIKE %s "
                "ORDER BY created_at DESC LIMIT 1",
                (f"%{project_title}%",),
            )
        else:
            cur.execute(
                "SELECT id, title, premise, genre FROM projects ORDER BY created_at DESC LIMIT 1"
            )
        return cur.fetchone()


def fetch_chapters_range(conn, project_id: str, from_num: int, to_num: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, content, sort_order, summary "
            "FROM chapters WHERE project_id = %s ORDER BY sort_order",
            (project_id,),
        )
        all_chapters = cur.fetchall()
    return [c for c in all_chapters if from_num - 1 <= c["sort_order"] <= to_num - 1]


def fetch_power_systems(conn, project_id: str) -> list:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, description, levels, special_rules, breakthrough_condition, "
            "protagonist_current_rank FROM power_systems WHERE project_id = %s ORDER BY sort_order",
            (project_id,),
        )
        return cur.fetchall()


def fetch_characters(conn, project_id: str, limit: int) -> list:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, role, current_realm, realm_rank, current_location, current_status "
            "FROM characters WHERE project_id = %s ORDER BY role, name LIMIT %s",
            (project_id, limit),
        )
        return cur.fetchall()


def fetch_storylines(conn, project_id: str, limit: int) -> list:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, line_type, status, core_conflict FROM storylines "
            "WHERE project_id = %s AND status IN ('active','climax','planned') "
            "ORDER BY sort_order LIMIT %s",
            (project_id, limit),
        )
        return cur.fetchall()


def fetch_chapter_indexes(conn, project_id: str, chapter_ids: list) -> dict:
    if not chapter_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT chapter_id, core_events, ending_hook, continuity_notes, story_day "
            "FROM chapter_indexes WHERE project_id = %s AND chapter_id = ANY(%s)",
            (project_id, chapter_ids),
        )
        rows = cur.fetchall()
    return {str(r["chapter_id"]): r for r in rows}


def build_power_system_text(power_systems: list) -> str:
    lines = []
    for ps in power_systems:
        levels = ps.get("levels") or []
        if isinstance(levels, str):
            try:
                levels = json.loads(levels)
            except Exception:
                levels = []
        level_names = []
        for lv in levels:
            if isinstance(lv, dict) and lv.get("name"):
                rank = lv.get("rank", "")
                level_names.append(f"{rank}.{lv['name']}" if rank else lv["name"])
        line = f"【{ps['name']}】"
        if level_names:
            line += " 等级顺序（从低到高）：" + " → ".join(level_names)
        if ps.get("protagonist_current_rank"):
            line += f"；主角当前 rank={ps['protagonist_current_rank']}"
        rules = ps.get("special_rules") or ps.get("breakthrough_condition") or ps.get("description") or ""
        if rules:
            line += f"；突破规则={rules[:200]}"
        lines.append(line)
    return "\n".join(lines) if lines else "（无境界体系数据）"


def build_character_text(characters: list) -> str:
    lines = []
    for c in characters:
        parts = [c["name"]]
        if c.get("role"):
            parts.append(f"身份={c['role']}")
        if c.get("current_realm"):
            parts.append(f"当前境界={c['current_realm']}")
        if c.get("current_location"):
            parts.append(f"当前位置={c['current_location']}")
        if c.get("current_status") and c["current_status"] != "alive":
            parts.append(f"状态={c['current_status']}")
        lines.append("；".join(parts))
    return "\n".join(lines) if lines else "（无人物数据）"


def build_storyline_text(storylines: list) -> str:
    lines = []
    for s in storylines:
        lines.append(f"- {s['name']}（{s['status']}）：{(s.get('core_conflict') or '')[:120]}")
    return "\n".join(lines) if lines else "（无故事线数据）"


def _sampling_limits(run_cfg: dict, large: bool) -> tuple[int, int, int, int, int, int]:
    s = run_cfg["sampling"]
    if large:
        head = int(s.get("head_chars_large_context", s["head_chars"]))
        tail = int(s.get("tail_chars_large_context", s["tail_chars"]))
    else:
        head = int(s["head_chars"])
        tail = int(s["tail_chars"])
    b_tail = int(s["boundary_snippet_tail"])
    b_head = int(s["boundary_snippet_head"])
    d_tail = int(s["boundary_deep_tail"])
    d_head = int(s["boundary_deep_head"])
    return head, tail, b_tail, b_head, d_tail, d_head


def build_evaluation_task_text(items: list[dict]) -> str:
    lines = []
    for i, it in enumerate(items, 1):
        title = it.get("title") or it.get("id", "")
        instr = it.get("instruction", "")
        lines.append(f"{i}. **{title}**：{instr}")
    return "\n".join(lines)


def build_issue_type_hint(items: list[dict]) -> str:
    ids = [it["id"] for it in items if it.get("id")]
    base = ", ".join(ids) if ids else "continuity_gap, realm_jump, character_swap, causality_missing, title_match"
    return (
        f"`cross_chapter_issues[].type` 优先使用配置中的 id：{base}；"
        "亦可使用 `logic_error` 表示无法归入以上类别的逻辑问题。"
    )


def build_main_system_prompt(run_cfg: dict) -> str:
    base = run_cfg["prompts"]["main_system_base"]
    items = run_cfg.get("evaluation_items") or []
    caps = "、".join((it.get("title") or it.get("id", "")) for it in items)
    if caps:
        return f"{base}\n\n本次核查维度包括：{caps}。"
    return base


async def call_ai(client, system: str, prompt: str, max_tokens: int = 4096) -> str:
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


async def full_coherence_check(
    client,
    project_title: str,
    chapters: list,
    power_text: str,
    char_text: str,
    storyline_text: str,
    indexes: dict,
    chapter_from: int,
    chapter_to: int,
    run_cfg: dict,
) -> dict:
    items = run_cfg.get("evaluation_items") or []
    head_n, tail_n, b_tail, b_head, _, _ = _sampling_limits(run_cfg, LARGE_CONTEXT)

    chapter_blocks = []
    ctx_flags = run_cfg["context"]
    use_index = ctx_flags.get("include_chapter_indexes", True)

    for c in chapters:
        ch_num = c["sort_order"] + 1
        title = c.get("title") or f"第{ch_num}章"
        content = c.get("content") or ""
        preview = head_tail(content, head_n, tail_n) if content else "（正文为空）"

        index_note = ""
        if use_index:
            idx = indexes.get(str(c["id"]))
            if idx:
                events_str = json.dumps(idx.get("core_events") or [], ensure_ascii=False)[:300]
                hook = (idx.get("ending_hook") or "")[:150]
                notes = json.dumps(idx.get("continuity_notes") or [], ensure_ascii=False)[:300]
                index_note = (
                    f"\n[章节索引] 核心事件={events_str}；章末钩子={hook}"
                    + (f"；连续性风险={notes}" if notes and notes != "[]" else "")
                )

        chapter_blocks.append(
            f"═══ 第{ch_num}章《{title}》（sort_order={c['sort_order']}）═══\n"
            f"{preview}{index_note}"
        )

    boundary_blocks = []
    for i in range(len(chapters) - 1):
        a = chapters[i]
        b = chapters[i + 1]
        num_a = a["sort_order"] + 1
        num_b = b["sort_order"] + 1
        tail_a = tail_only(a.get("content") or "", b_tail)
        head_b = head_only(b.get("content") or "", b_head)
        if tail_a or head_b:
            boundary_blocks.append(
                f"── 衔接点 {num_a}→{num_b} ──\n"
                f"[第{num_a}章 末尾{b_tail}字]\n{tail_a or '（无内容）'}\n\n"
                f"[第{num_b}章 开头{b_head}字]\n{head_b or '（无内容）'}"
            )

    chapters_text = "\n\n".join(chapter_blocks)
    boundaries_text = "\n\n".join(boundary_blocks)

    system = build_main_system_prompt(run_cfg)
    task_block = build_evaluation_task_text(items)
    type_hint = build_issue_type_hint(items)

    power_section = (
        f"═══════════ 境界体系（必须严格核验，不得跨级跳变）═══════════\n{power_text}"
        if run_cfg["context"].get("include_power_systems", True)
        else "═══════════ 境界体系 ═══════════\n（本评测配置已关闭境界体系上下文；请勿做境界跳变判定。）"
    )
    char_section = (
        f"═══════════ 人物当前状态（供一致性基线）═══════════\n{char_text}"
        if run_cfg["context"].get("include_characters", True)
        else "═══════════ 人物 ═══════════\n（本评测配置已关闭人物表上下文。）"
    )
    story_section = (
        f"═══════════ 活跃故事线 ═══════════\n{storyline_text}"
        if run_cfg["context"].get("include_storylines", True)
        else "═══════════ 故事线 ═══════════\n（本评测配置已关闭故事线上下文。）"
    )

    prompt = f"""小说：《{project_title}》
评测范围：第{chapter_from}章 ~ 第{chapter_to}章（共{len(chapters)}章）

{power_section}

{char_section}

{story_section}

═══════════ 各章正文摘要（首段+尾段，附索引）═══════════
{chapters_text}

═══════════ 相邻章节衔接对（前章末{b_tail}字 vs 后章开头{b_head}字）═══════════
{boundaries_text}

════════════ 评测任务 ════════════
请逐一核查以下问题，并在 cross_chapter_issues 中给出精准定位：

{task_block}

{type_hint}

返回 JSON（字段名固定）：
{{
  "overall_score": 7.0,
  "continuity_score": 6.5,
  "title_match_score": 8.0,
  "chapter_evaluations": [
    {{
      "chapter_number": 11,
      "chapter_title": "...",
      "title_match_score": 8,
      "title_match_comment": "标题与正文是否匹配",
      "risk_level": "low/medium/high"
    }}
  ],
  "cross_chapter_issues": [
    {{
      "type": "使用上文所列 id 或 logic_error",
      "severity": "low/medium/high/critical",
      "chapters_involved": [11, 12],
      "description": "详细描述：前章末尾写了什么，后章开头写了什么，断层在哪里",
      "suggested_fix": "具体修复建议"
    }}
  ],
  "suggestions": ["按优先级给出可执行修改建议"],
  "summary": "一句话总评"
}}"""

    max_tok = 8192 if LARGE_CONTEXT else 4096
    response = await call_ai(client, system, prompt, max_tokens=max_tok)
    try:
        return parse_json_response(response)
    except Exception as e:
        return {
            "overall_score": 0,
            "error": f"JSON 解析失败: {e}",
            "raw_response": response[:1000],
        }


def build_boundary_checklist(run_cfg: dict) -> str:
    lines = []
    n = 1
    for it in run_cfg.get("evaluation_items") or []:
        if not it.get("include_in_boundary_prompt", False):
            continue
        title = it.get("title") or it.get("id", "")
        instr = it.get("instruction", "")
        lines.append(f"{n}. **{title}**：{instr}")
        n += 1
    if not lines:
        return (
            "1. 场景是否自然衔接（时间、地点、人物是否有断层）\n"
            "2. 前章末尾涉及的人物/冲突，后章开头是否有合理承接？\n"
            "3. 境界/状态是否有不合理跳变？\n"
            "4. 是否有角色姓名/身份替换？"
        )
    return "\n".join(lines)


async def boundary_detail_check(
    client,
    chapter_a: dict,
    chapter_b: dict,
    power_text: str,
    run_cfg: dict,
) -> dict:
    _, _, _, _, d_tail, d_head = _sampling_limits(run_cfg, LARGE_CONTEXT)
    num_a = chapter_a["sort_order"] + 1
    num_b = chapter_b["sort_order"] + 1
    tail_a = tail_only(chapter_a.get("content") or "", d_tail)
    head_b = head_only(chapter_b.get("content") or "", d_head)

    system = run_cfg["prompts"]["boundary_system"]
    checklist = build_boundary_checklist(run_cfg)
    use_power = run_cfg["context"].get("include_power_systems", True)
    power_block = (
        f"境界体系（用于核验境界跳变）：\n{power_text}"
        if use_power
        else "（本评测配置已关闭境界体系；请勿做境界跳变判定。）"
    )

    prompt = f"""请精细分析第{num_a}章末尾与第{num_b}章开头的衔接：

{power_block}

第{num_a}章《{chapter_a.get('title', '')}》末尾{d_tail}字：
{tail_a or '（无内容）'}

第{num_b}章《{chapter_b.get('title', '')}》开头{d_head}字：
{head_b or '（无内容）'}

请检查：
{checklist}

返回 JSON：
{{
  "has_issue": true,
  "severity": "low/medium/high/critical",
  "issues": [
    {{
      "type": "continuity_gap/realm_jump/character_swap/causality_missing/logic_error",
      "description": "具体描述：前章末尾写了X，后章开头却是Y，缺少Z的交代",
      "suggested_fix": "具体修复建议"
    }}
  ],
  "summary": "一句话概括衔接质量"
}}"""

    response = await call_ai(client, system, prompt, max_tokens=2048)
    try:
        result = parse_json_response(response)
        result["chapters"] = [num_a, num_b]
        return result
    except Exception as e:
        return {"has_issue": False, "error": str(e), "chapters": [num_a, num_b]}


async def run_evaluation(
    chapter_from: int,
    chapter_to: int,
    run_cfg: dict,
    project_id: Optional[str],
    project_title: Optional[str],
    output_path: Optional[str],
    skip_followup: bool,
):
    _require_openai()
    if not MODEL:
        sys.exit(
            "未检测到可用模型。\n"
            "请在 apps/backend/.env 中设置 AI_MODEL（本地）或 GEMINI_MODEL（远程）。"
        )

    print(f"\n{'='*60}")
    print(f"  跨章连贯性评测 — 第{chapter_from}~{chapter_to}章")
    print(f"  模型: {MODEL} ({'大上下文' if LARGE_CONTEXT else '本地'})")
    src = run_cfg.get("_loaded_from")
    print(f"  配置: {src or '内置默认（未找到配置文件）'}")
    print(f"{'='*60}\n")

    print("📡 连接数据库...")
    try:
        conn = get_db_conn()
    except Exception as e:
        sys.exit(f"数据库连接失败: {e}\n请确保 PostgreSQL 服务正在运行，DATABASE_URL={DB_URL}")

    project = fetch_project(conn, project_id=project_id, project_title=project_title)
    if not project:
        sys.exit("数据库中没有找到匹配的项目（请检查 --project-id / --project-title）")
    print(f"📚 项目：《{project['title']}》（{project.get('genre', '')}） id={project['id']}")

    chapters = fetch_chapters_range(conn, str(project["id"]), chapter_from, chapter_to)
    if not chapters:
        sys.exit(f"未找到第{chapter_from}~{chapter_to}章，请检查数据库中是否有对应数据")
    print(f"📖 找到 {len(chapters)} 章（sort_order: {chapters[0]['sort_order']} ~ {chapters[-1]['sort_order']}）")

    ctx = run_cfg["context"]
    pid = str(project["id"])
    power_systems = fetch_power_systems(conn, pid) if ctx.get("include_power_systems", True) else []
    characters = (
        fetch_characters(conn, pid, int(ctx.get("character_limit", 20)))
        if ctx.get("include_characters", True)
        else []
    )
    storylines = (
        fetch_storylines(conn, pid, int(ctx.get("storyline_limit", 10)))
        if ctx.get("include_storylines", True)
        else []
    )
    chapter_ids = [str(c["id"]) for c in chapters]
    indexes = (
        fetch_chapter_indexes(conn, pid, chapter_ids)
        if ctx.get("include_chapter_indexes", True)
        else {}
    )

    conn.close()

    power_text = build_power_system_text(power_systems)
    char_text = build_character_text(characters)
    storyline_text = build_storyline_text(storylines)

    if ctx.get("include_power_systems", True):
        print(f"\n境界体系概览:\n{power_text[:400]}\n")

    import httpx

    http_client = httpx.AsyncClient(timeout=httpx.Timeout(connect=15, read=180, write=60, pool=30))
    ai_client = openai.AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY, http_client=http_client)

    print("🔍 Step 1/3: 主连贯性评测（全章范围）...")
    main_result = await full_coherence_check(
        ai_client,
        project["title"],
        chapters,
        power_text,
        char_text,
        storyline_text,
        indexes,
        chapter_from,
        chapter_to,
        run_cfg,
    )

    follow = run_cfg.get("followup") or {}
    do_followup = follow.get("enabled", True) and not skip_followup
    boundary_results = []
    high_risk_pairs: set[tuple[int, int]] = set()

    if do_followup:
        sev_tr = set(follow.get("severity_triggers") or ["high", "critical"])
        risk_tr = set(follow.get("risk_level_triggers") or ["high"])
        n_always = int(follow.get("always_first_n_boundaries", 3))

        for issue in main_result.get("cross_chapter_issues", []):
            if issue.get("severity") in sev_tr:
                involved = issue.get("chapters_involved", [])
                if len(involved) >= 2:
                    high_risk_pairs.add((int(involved[0]), int(involved[1])))

        for ev in main_result.get("chapter_evaluations", []):
            if ev.get("risk_level") in risk_tr:
                num = ev.get("chapter_number")
                if num:
                    num = int(num)
                    if num > chapter_from:
                        high_risk_pairs.add((num - 1, num))
                    if num < chapter_to:
                        high_risk_pairs.add((num, num + 1))

        for i in range(min(n_always, len(chapters) - 1)):
            num_a = chapters[i]["sort_order"] + 1
            num_b = chapters[i + 1]["sort_order"] + 1
            high_risk_pairs.add((num_a, num_b))

        if high_risk_pairs:
            print(f"🔬 Step 2/3: 细粒度衔接深挖（{len(high_risk_pairs)} 个衔接点）...")
            chapter_map = {c["sort_order"] + 1: c for c in chapters}
            for num_a, num_b in sorted(high_risk_pairs):
                if num_a in chapter_map and num_b in chapter_map:
                    print(f"   → 衔接点 {num_a}→{num_b}")
                    br = await boundary_detail_check(
                        ai_client,
                        chapter_map[num_a],
                        chapter_map[num_b],
                        power_text,
                        run_cfg,
                    )
                    boundary_results.append(br)
    else:
        print("⏭️  Step 2/3: 已跳过衔接深挖（配置或 --skip-followup）")

    print("\n📊 Step 3/3: 汇总结果...\n")

    slug = project_slug(project["title"])
    tmpl = (run_cfg.get("output") or {}).get(
        "report_filename_template",
        "coherence_report_{project_slug}_ch{chapter_from}_{chapter_to}.json",
    )
    default_name = tmpl.format(
        project_slug=slug, chapter_from=chapter_from, chapter_to=chapter_to
    )
    out_path = output_path or os.path.join(os.path.dirname(__file__), default_name)

    final = {
        "evaluation_range": f"第{chapter_from}~{chapter_to}章",
        "chapter_count": len(chapters),
        "project_id": str(project["id"]),
        "model_used": MODEL,
        "large_context": LARGE_CONTEXT,
        "config_path": run_cfg.get("_loaded_from"),
        "main_evaluation": main_result,
        "boundary_deep_dives": boundary_results,
    }

    print("=" * 60)
    print("【评测结果摘要】")
    print("=" * 60)
    print(f"综合评分:   {main_result.get('overall_score', 'N/A')}/10")
    print(f"连贯性评分: {main_result.get('continuity_score', 'N/A')}/10")
    print(f"标题匹配:   {main_result.get('title_match_score', 'N/A')}/10")
    print(f"总评: {main_result.get('summary', '')}\n")

    issues = main_result.get("cross_chapter_issues", [])
    if issues:
        print(f"⚠️  发现跨章问题 ({len(issues)} 个)：")
        for i, issue in enumerate(issues, 1):
            severity = issue.get("severity", "?")
            emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(severity, "⚪")
            chapters_str = "→".join(str(x) for x in (issue.get("chapters_involved") or []))
            print(f"\n  {i}. {emoji} [{severity.upper()}] 第{chapters_str}章 | 类型: {issue.get('type', '')}")
            print(f"     描述: {issue.get('description', '')}")
            print(f"     建议: {issue.get('suggested_fix', '')}")
    else:
        print("✅ 主评测未发现明显跨章问题")

    if boundary_results:
        print("\n🔬 衔接点细粒度结果：")
        for br in boundary_results:
            chs = "→".join(str(x) for x in br.get("chapters", []))
            has_issue = br.get("has_issue", False)
            sev = br.get("severity", "low")
            emoji = "⚠️ " if has_issue else "✅"
            print(f"\n  {emoji} 第{chs}章衔接 [{sev}]: {br.get('summary', '')}")
            for iss in br.get("issues") or []:
                print(f"    - [{iss.get('type')}] {iss.get('description', '')}")
                if iss.get("suggested_fix"):
                    print(f"      修复: {iss.get('suggested_fix', '')}")

    suggestions = main_result.get("suggestions", [])
    if suggestions:
        print("\n📝 修改建议：")
        for i, s in enumerate(suggestions, 1):
            print(f"  {i}. {s}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"\n💾 完整 JSON 报告已保存: {out_path}")
    await http_client.aclose()


def cmd_list_projects():
    try:
        conn = get_db_conn()
    except Exception as e:
        sys.exit(f"数据库连接失败: {e}")
    rows = list_projects(conn)
    conn.close()
    if not rows:
        print("（无项目）")
        return
    for r in rows:
        print(f"{r['id']}\t{r.get('title','')}\t{r.get('genre','')}")


def main():
    parser = argparse.ArgumentParser(description="通用跨章连贯性评测（配置驱动）")
    parser.add_argument("--from", dest="chapter_from", type=int, default=11, help="起始章节号（默认 11）")
    parser.add_argument("--to", dest="chapter_to", type=int, default=20, help="结束章节号（默认 20）")
    parser.add_argument("--config", type=str, default=None, help="JSON 配置文件路径（默认脚本旁 coherence_check_config.json）")
    parser.add_argument("--project-id", type=str, default=None, help="指定项目 UUID")
    parser.add_argument(
        "--project-title",
        type=str,
        default=None,
        help="按标题模糊匹配项目（ILIKE %%关键词%%，取最新一条）",
    )
    parser.add_argument("--list-projects", action="store_true", help="列出数据库中的项目后退出")
    parser.add_argument("--output", "-o", type=str, default=None, help="报告 JSON 输出路径")
    parser.add_argument("--skip-followup", action="store_true", help="跳过衔接点二次深挖")
    args = parser.parse_args()

    if args.list_projects:
        cmd_list_projects()
        return

    run_cfg = load_run_config(args.config)
    asyncio.run(
        run_evaluation(
            args.chapter_from,
            args.chapter_to,
            run_cfg,
            args.project_id,
            args.project_title,
            args.output,
            args.skip_followup,
        )
    )


if __name__ == "__main__":
    main()
