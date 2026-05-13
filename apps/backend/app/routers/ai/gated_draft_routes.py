"""
gated_draft_routes.py — 质量门控写作端点

资源边界：
  - 本模块负责「写前预警 → 起笔 → 自动质检 → 未达标则重写 → 循环」的全链路编排。
  - 单次起笔/续写（无循环）仍走 draft_routes.draft-assist/stream。
  - 质检逻辑复用 AIService.quality_check；存库逻辑内联（避免额外 HTTP 跳转）。

SSE 协议（JSON lines，prefix: ``data: ``）：
  gate_config       — 循环开始前推送生效配置（含 block_on_consistency_issues、hook_mandate_active 等）
  pre_warn_running  — 写前预警开始（仅当 pre_write_warning_enabled=true）
  pre_warn_done     — 写前预警完成，附 risk_count / ok / protagonist_fact_sheet / writing_brief
  attempt_start     — 本轮起笔开始（strategy: initial | patch | full_rewrite）
  text              — 正文片段（与普通 draft-assist 格式完全一致）
  attempt_done      — 本轮起笔结束，附字数
  qc_running        — 质检开始
  qc_result         — 质检结果（passed / score / subscribe_intent / suggestions）
  gate_passed       — 达标，循环结束
  rewrite_queued    — 未达标，即将进行下一轮（附策略）
  gate_failed       — 达到最大次数仍未达标，章节置 needs_review
  error             — 不可恢复错误
  [DONE]            — 流结束标记
"""
from __future__ import annotations

import json
import re
import textwrap
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Chapter,
    ChapterVersion,
    Character,
    Foreshadow,
    Location,
    MemoryChunk,
    OutlineNode,
    PowerSystem,
    Project,
    StoryLine,
    WorldSetting,
)
from app.routers.ai.context import (
    build_chapter_index_context,
    build_continuity_context,
    build_plot_dossier_context,
    format_world_setting_context,
)
from app.routers.ai.draft_routes import _build_draft_context
from app.routers.ai.draft_helpers import (
    hook_chapter_mandate_active,
    merge_writing_config,
    prewrite_gate_violation,
)
from app.services.embedding_service import semantic_search as _semantic_search
from app.routers.ai.quality_debt import sync_quality_debts
from app.routers.ai.schemas import GatedDraftRequest
from app.routers.ai.text_utils import plain_text
from app.services.ai_service import AIService
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block

router = APIRouter()


def _count_words_plain(text: str) -> int:
    """简易中文字数统计（去 HTML 标签）。"""
    clean = re.sub(r"<[^>]+>", "", text or "")
    chinese = len(re.findall(r"[一-鿿]", clean))
    english = len(re.findall(r"[a-zA-Z]+", clean))
    return chinese + english


async def _run_pre_write_warning_inline(
    db: Session,
    chapter: Chapter,
    project: Project,
    project_id: str,
    svc: AIService,
) -> dict:
    """
    在门控写作开始前内联执行写前预警，不走 HTTP 路由。

    组装与 quality_routes.pre_write_warning 端点相同的上下文（记忆/伏笔/人物/境界），
    调用 AIService.pre_write_warning，返回结果 dict（含 protagonist_fact_sheet /
    writing_brief / must_events / hallucination_traps / risks / reminders）。

    @param db: SQLAlchemy Session
    @param chapter: 已加载的 Chapter 对象
    @param project: 已加载的 Project 对象
    @param project_id: 项目 UUID 字符串
    @param svc: 已初始化的 AIService 实例
    @returns pre_write_warning 返回的 dict
    @raises Exception: AI 调用失败时向上抛出
    """
    # 记忆：用章节 outline 摘要做语义检索，优先拉与本章相关的记忆；
    # max_chapter=chapter.sort_order 防伏笔泄漏；semantic_search 内部已有时序兜底。
    _outline_node = None
    if chapter.outline_node_id:
        from app.models import OutlineNode as _OutlineNode
        _outline_node = db.query(_OutlineNode).filter(
            _OutlineNode.id == chapter.outline_node_id
        ).first()
    _warn_query = " ".join(filter(None, [
        _outline_node.summary if _outline_node else None,
        _outline_node.conflict if _outline_node else None,
    ])) or chapter.title or ""
    _raw_mems = await _semantic_search(
        db, project_id, _warn_query,
        top_k=40,
        max_chapter=chapter.sort_order,
    ) if _warn_query else []
    memory_chunks = [
        {"title": m.title or "", "content": m.content or "", "memory_type": m.memory_type or "event"}
        for m in _raw_mems
    ]

    # 未回收伏笔
    open_foreshadows = (
        db.query(Foreshadow)
        .filter(Foreshadow.project_id == project_id, Foreshadow.status == "open")
        .order_by(Foreshadow.priority.desc())
        .limit(30)
        .all()
    )
    foreshadow_lines = []
    ch_no = chapter.sort_order or 0
    for f in open_foreshadows:
        code = f.code or "—"
        overdue = "【⚠️已逾期】" if (f.planned_resolve_chapter and ch_no > 0 and f.planned_resolve_chapter <= ch_no) else ""
        foreshadow_lines.append(
            f"{overdue}{code} {f.title or ''} | 预计第{f.planned_resolve_chapter or '?'}章回收 | {(f.description or '')[:100]}"
        )
    foreshadow_ledger = "\n".join(foreshadow_lines)

    # 人物状态（含技能/道具）
    characters = db.query(Character).filter(Character.project_id == project_id).all()

    def _names_brief(lst, key: str) -> str:
        if not lst:
            return ""
        return "、".join(
            (x.get(key, "") if isinstance(x, dict) else str(x))
            for x in lst[:6] if x
        )

    char_lines = []
    for c in characters[:12]:
        line = f"{c.name}：境界={c.current_realm or '?'}，位置={c.current_location or '?'}，状态={c.current_status or 'alive'}"
        sk = _names_brief(c.known_skills, "skill_name")
        if sk:
            line += f"，技能=[{sk}]"
        it = _names_brief(c.owned_items, "item_name")
        if it:
            line += f"，持有=[{it}]"
        char_lines.append(line)
    character_states = "\n".join(char_lines)

    # 境界体系摘要
    power_systems = db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()
    ps_lines = []
    for ps in power_systems:
        levels = []
        for lv in (ps.levels or [])[:20]:
            levels.append(lv.get("name") or "" if isinstance(lv, dict) else str(lv))
        rule = ps.special_rules or ps.breakthrough_condition or ps.description or ""
        ps_lines.append(
            f"{ps.name}：境界序列=[{' < '.join(l for l in levels if l)}]；"
            f"主角当前={ps.protagonist_current_rank or '未知'}；规则={rule[:120]}"
        )
    power_systems_summary = "\n".join(ps_lines)

    # 大纲五要素
    outline_context = ""
    phase = ""
    outline_node: OutlineNode | None = None
    if chapter.outline_node_id:
        outline_node = db.query(OutlineNode).filter(OutlineNode.id == chapter.outline_node_id).first()
        if outline_node:
            parts = []
            if outline_node.summary:
                parts.append(f"概述：{outline_node.summary}")
            if outline_node.hook:
                parts.append(f"开篇钩子：{outline_node.hook}")
            if outline_node.conflict:
                parts.append(f"核心冲突：{outline_node.conflict}")
            if outline_node.highlight:
                parts.append(f"章末方向：{outline_node.highlight}")
            if outline_node.power_milestone:
                parts.append(f"实力里程碑：{outline_node.power_milestone}")
            if outline_node.emotional_tone:
                parts.append(f"情感基调：{outline_node.emotional_tone}")
            outline_context = "\n".join(parts)
            phase = getattr(outline_node, "phase", None) or (outline_node.extra or {}).get("phase") or ""
    if not phase and outline_node and outline_node.parent_id:
        vol = db.query(OutlineNode).filter(OutlineNode.id == outline_node.parent_id).first()
        if vol:
            phase = getattr(vol, "phase", None) or (vol.extra or {}).get("phase") or ""

    # 连续性账本
    story_core = project.story_core if isinstance(project.story_core, dict) else {}
    continuity_state = str(story_core.get("rolling_continuity_state", ""))

    # 大纲五要素兜底（无 outline_node 时用章节标题）
    chapter_plan_summary = outline_context or f"第{chapter.sort_order or '?'}章《{chapter.title}》"

    return await svc.pre_write_warning(
        project_title=project.title,
        genre=project.genre or "玄幻",
        chapter_plan_summary=chapter_plan_summary,
        memory_chunks=memory_chunks,
        continuity_state=continuity_state,
        foreshadow_ledger=foreshadow_ledger,
        character_states=character_states,
        power_systems_summary=power_systems_summary,
        outline_context=outline_context,
        phase=phase,
    )


def _build_pre_warn_prompt_block(warn_result: dict) -> str:
    """
    将写前预警结果格式化为注入首次起笔 prompt 的「写前简报」块。

    不重复向 AI 展示完整的 JSON，只提取对写正文最关键的信息：
    - 主角状态锁定（protagonist_fact_sheet）
    - 本章写法简报（writing_brief）
    - 必发事件（must_events）
    - 幻觉预防清单（hallucination_traps）
    - 高危/中危风险（risks severity>=medium）

    @param warn_result: pre_write_warning 返回的 dict
    @returns 格式化文本块（用于拼入 user_prompt）
    """
    lines: list[str] = ["\n\n===【写前简报（由30年主编生成，写正文时必须严格遵守）】==="]

    # ① 主角状态锁定
    pfs = warn_result.get("protagonist_fact_sheet") or {}
    if isinstance(pfs, dict):
        lines.append("\n▍主角状态锁定（本章开笔时的精确状态，不得幻觉升级或改动）")
        if pfs.get("realm"):
            lines.append(f"  境界：{pfs['realm']}")
        if pfs.get("location"):
            lines.append(f"  位置：{pfs['location']}")
        if pfs.get("key_skills"):
            lines.append("  本章可用技能：" + "；".join(pfs["key_skills"][:5]))
        if pfs.get("key_items"):
            lines.append("  持有道具：" + "；".join(pfs["key_items"][:5]))
        if pfs.get("forbidden"):
            lines.append("  ⛔ 本章禁止出现：" + "；".join(pfs["forbidden"][:5]))

    # ② 本章写作简报
    wb = warn_result.get("writing_brief") or {}
    if isinstance(wb, dict) and any(wb.values()):
        lines.append("\n▍本章写作指导")
        if wb.get("opening_strategy"):
            lines.append(f"  开篇策略：{wb['opening_strategy']}")
        if wb.get("conflict_structure"):
            lines.append(f"  冲突节拍：{wb['conflict_structure']}")
        if wb.get("closing_hook"):
            lines.append(f"  章末钩子：{wb['closing_hook']}")
        if wb.get("word_rhythm"):
            lines.append(f"  字数节奏：{wb['word_rhythm']}")

    # ③ 必发事件
    must_events = warn_result.get("must_events") or []
    if must_events:
        lines.append("\n▍本章必须发生的事件（逐条落实，不得遗漏）")
        for i, ev in enumerate(must_events[:4], 1):
            lines.append(f"  {i}. {ev}")

    # ④ 幻觉预防
    traps = warn_result.get("hallucination_traps") or []
    if traps:
        lines.append("\n▍常见幻觉预防（逐条注意）")
        for trap in traps[:5]:
            lines.append(f"  • {trap}")

    # ⑤ 高危/中危风险
    risks = [r for r in (warn_result.get("risks") or []) if r.get("severity") in ("high", "critical", "medium")]
    if risks:
        lines.append("\n▍需处理的风险（severity medium/high/critical）")
        for r in risks[:5]:
            lines.append(f"  [{r.get('severity','?')}·{r.get('type','?')}] {r.get('description','')}")
            if r.get("suggested_fix"):
                lines.append(f"    建议：{r['suggested_fix']}")

    lines.append("===")
    return "\n".join(lines)


def _build_location_context(db: Session, project_id: str) -> str:
    """
    构造空间连续性约束块，注入写章 prompt。

    逻辑：
    1. 查询项目内所有 Character（最多 12 个）的 current_location 字段；
    2. 对每个非空 current_location，尝试在 locations 表中按名称/别名模糊匹配；
    3. 若匹配到 Location，提取 danger_level + sensory_signature 作为感官基准；
    4. 组装成「⚠️ 空间连续性约束」块，写章时 AI 必须遵守。

    空返回值（空字符串）：项目无角色、所有角色位置为空，或数据库中无任何 Location 记录时返回 ""。

    @param db: SQLAlchemy Session
    @param project_id: 项目 UUID 字符串
    @returns 格式化约束文本块；无有效数据时返回空字符串
    """
    characters = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.realm_rank.desc().nullslast())  # 主角/高境界角色优先
        .limit(12)
        .all()
    )

    char_locs: list[tuple[str, str]] = [
        (c.name, (c.current_location or "").strip())
        for c in characters
        if (c.current_location or "").strip()
    ]
    if not char_locs:
        return ""

    # 预加载项目内所有 Location，用于名称匹配（数量通常 < 100，全量拉取可接受）
    all_locations = (
        db.query(Location)
        .filter(Location.project_id == project_id)
        .all()
    )

    def _match_location(loc_text: str) -> Location | None:
        """按精确名 → 别名包含 → 名称包含的优先级依次匹配。"""
        loc_lower = loc_text.lower()
        for loc in all_locations:
            if loc.name.lower() == loc_lower:
                return loc
        for loc in all_locations:
            aliases = loc.aliases or []
            if any(a.lower() == loc_lower for a in aliases):
                return loc
        for loc in all_locations:
            if loc.name.lower() in loc_lower or loc_lower in loc.name.lower():
                return loc
        return None

    danger_labels = {
        "safe": "安全",
        "neutral": "中性",
        "dangerous": "危险",
        "forbidden": "禁区",
    }

    # 按展示地点合并多人：「张三、李四所在：」+ 同一条地点/感官行，避免重复块浪费上下文。
    groups: dict[str, dict] = {}
    group_order: list[str] = []

    for char_name, loc_text in char_locs:
        matched = _match_location(loc_text)
        loc_display = matched.name if matched else loc_text
        danger = ""
        sensory = ""
        if matched:
            danger = f"危险等级：{danger_labels.get(matched.danger_level or 'neutral', matched.danger_level)}"
            sensory = (matched.sensory_signature or "").strip()

        entry_key = loc_display.lower()
        if entry_key not in groups:
            groups[entry_key] = {
                "names": [char_name],
                "loc_display": loc_display,
                "danger": danger,
                "sensory": sensory,
            }
            group_order.append(entry_key)
        else:
            groups[entry_key]["names"].append(char_name)

    lines: list[str] = []
    for entry_key in group_order:
        g = groups[entry_key]
        names_joined = "、".join(g["names"])
        loc_line = f"  - {g['loc_display']}" + (f"（{g['danger']}）" if g["danger"] else "")
        if g["sensory"]:
            loc_line += f"\n    感官基准：{g['sensory']}"
        lines.append(f"{names_joined}所在：\n{loc_line}")

    if not lines:
        return ""

    block = (
        "【⚠️ 空间连续性约束（必须遵守）】\n"
        "本章起始空间状态（来自上章复盘提取）：\n"
        + "\n".join(lines)
        + "\n⚠️ 严禁在未交代过渡（如传送/赶路场景）的情况下改变角色所在地。"
        "如需切换场景，必须写明位移动作或明确时间跳跃标注。\n"
        "⚠️ 有感官基准的地点：正文中该地点的气味/光线/声音/温度描写，必须与「感官基准」保持一致，"
        "不得引入矛盾感官细节。"
    )
    return block


def _plain_text_from_html(html: str) -> str:
    """HTML → 纯文本（去标签、保留换行语义）。"""
    text = re.sub(r"<br\s*/?>", "\n", html or "")
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _save_chapter_content(db: Session, chapter: Chapter, plain_draft: str, attempt: int) -> None:
    """
    将本轮生成的纯文本稿保存到 Chapter，并创建 ChapterVersion 快照。

    @param db: SQLAlchemy Session
    @param chapter: Chapter ORM 对象（将被就地修改）
    @param plain_draft: 本轮生成的纯文本正文（不含索引块）
    @param attempt: 当前尝试次数（写入快照 note）
    """
    # 纯文本 → HTML（每段一 <p>）
    blocks = plain_draft.split("\n\n")
    html_content = "\n".join(
        f"<p>{b.strip().replace(chr(10), '<br>')}</p>"
        for b in blocks if b.strip()
    ) or "<p></p>"

    word_count = _count_words_plain(plain_draft)

    # 先快照旧内容（首轮如果有旧内容）
    if chapter.content and chapter.content.strip():
        snap = ChapterVersion(
            chapter_id=chapter.id,
            content=chapter.content,
            word_count=_count_words_plain(_plain_text_from_html(chapter.content)),
            note=f"质量门控第{attempt}轮起笔前自动备份",
            is_auto=True,
        )
        db.add(snap)

    chapter.content = html_content
    chapter.manuscript_raw_snapshot = plain_draft
    chapter.word_count = word_count
    chapter.status = "writing"
    chapter.gated_draft_attempts = attempt
    db.commit()
    db.refresh(chapter)


async def _run_quality_check_inline(
    db: Session,
    chapter: Chapter,
    project: Project,
    project_id: str,
    large_context: bool,
    svc: AIService,
) -> dict:
    """
    在 gated 循环中内联执行质检，不走 HTTP 路由。

    复用 AIService.quality_check；上下文组装与 quality_routes 保持一致。

    @param db: SQLAlchemy Session
    @param chapter: 已保存最新内容的 Chapter 对象
    @param project: Project 对象
    @param project_id: 项目 UUID 字符串
    @param large_context: 是否大上下文模式（gemini）
    @param svc: 已初始化的 AIService 实例
    @returns quality_check 返回的 dict（含 overall_score / dimensions / suggestions / issues）
    @raises Exception: AI 调用失败时向上抛出
    """
    memory_query = (
        db.query(MemoryChunk)
        .outerjoin(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(MemoryChunk.project_id == project_id)
        .order_by(func.coalesce(Chapter.sort_order, MemoryChunk.chapter_number, 0).asc())
    )
    memories = memory_query.limit(200 if large_context else 50).all()

    settings = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id
    ).all()

    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()

    def _skill_names(known_skills) -> str:
        if not known_skills:
            return "无"
        names = [
            sk.get("skill_name", "") if isinstance(sk, dict) else str(sk)
            for sk in known_skills[:5]
        ]
        return "、".join(n for n in names if n) or "无"

    character_states = [
        f"{c.name}：境界={c.current_realm or '未知'}，"
        f"位置={c.current_location or '未知'}，"
        f"状态={c.current_status or 'alive'}，"
        f"已知技能=[{_skill_names(c.known_skills)}]"
        for c in characters
    ]

    active_storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["active", "climax"])
    ).all()
    storylines_context = [
        f"{s.name}（{s.line_type}，{s.status}）：{s.core_conflict or s.description or ''}"
        for s in active_storylines
    ]

    power_systems = db.query(PowerSystem).filter(
        PowerSystem.project_id == project_id
    ).all()
    power_systems_summary = []
    for ps in power_systems:
        if large_context:
            levels = []
            for level in (ps.levels or []):
                if isinstance(level, dict):
                    rank = level.get("rank")
                    name = level.get("name") or ""
                    req_str = level.get("requirement") or level.get("description") or ""
                    levels.append(f"{rank}.{name}({req_str})" if rank else f"{name}({req_str})")
                else:
                    levels.append(str(level))
            rules = ps.special_rules or ps.breakthrough_condition or ps.description or ""
            power_systems_summary.append(
                f"{ps.name}：等级={' > '.join(levels) or '未知'}；"
                f"主角当前={ps.protagonist_current_rank or '未知'}；规则={rules}"
            )
        else:
            highest_level = "未知"
            if ps.levels:
                last_level = ps.levels[-1]
                if isinstance(last_level, dict):
                    highest_level = last_level.get("name", "") or "未知"
                else:
                    highest_level = str(last_level) or "未知"
            power_systems_summary.append(
                f"{ps.name}：最高境界={highest_level}，主角当前={ps.protagonist_current_rank or '未知'}"
            )

    # 大纲上下文
    outline_context = ""
    node: OutlineNode | None = None
    if chapter.outline_node_id:
        node = db.query(OutlineNode).filter(OutlineNode.id == chapter.outline_node_id).first()
        if node:
            parts = []
            if node.summary:
                parts.append(f"本章摘要：{node.summary}")
            if large_context and node.hook:
                parts.append(f"开篇钩子：{node.hook}")
            if large_context and node.conflict:
                parts.append(f"核心冲突：{node.conflict}")
            if large_context and node.highlight:
                parts.append(f"章末方向：{node.highlight}")
            if node.power_milestone:
                parts.append(f"实力里程碑：{node.power_milestone}")
            if node.emotional_tone:
                parts.append(f"情感基调：{node.emotional_tone}")
            if node.foreshadows_laid:
                foreshadow_descs = [
                    f.get("description", "") if isinstance(f, dict) else str(f)
                    for f in node.foreshadows_laid[:3]
                ]
                parts.append(f"本章埋下伏笔：{'；'.join(foreshadow_descs)}")
            outline_context = "；".join(parts)

    continuity_ctx = build_continuity_context(
        db=db, project_id=project_id, chapter=chapter, outline_node=node,
    )
    chapter_index_ctx = build_chapter_index_context(
        db=db, project_id=project_id, chapter=chapter,
    )
    plot_dossier_ctx = build_plot_dossier_context(
        db=db, project_id=project_id, chapter=chapter, large_context=large_context,
    )

    check_types = [
        "plot", "character", "setting_consistency", "pacing",
        "hooks", "outline_alignment", "face_slap_payoff",
        "emotional_resonance", "subscribe_intent",
    ]

    result = await svc.quality_check(
        chapter_content=chapter.content,
        chapter_title=chapter.title,
        memories=[m.content for m in memories],
        settings_summary=[
            format_world_setting_context(s, content_limit=2400 if large_context else 260)
            for s in settings
        ],
        check_types=check_types,
        character_states=character_states,
        storylines_context=storylines_context,
        power_systems_summary=power_systems_summary,
        outline_context=outline_context,
        continuity_context=continuity_ctx,
        chapter_index_context=chapter_index_ctx,
        plot_dossier_context=plot_dossier_ctx,
    )

    # 写库（复用 quality_routes 逻辑）
    chapter.last_quality_score = result.get("overall_score")
    chapter.last_quality_report = result
    chapter.quality_checked_at = func.now()
    sync_quality_debts(db, project_id, chapter, result)
    db.commit()
    db.refresh(chapter)

    return result


def _check_passed(
    qc_result: dict,
    cfg: dict,
    *,
    hook_mandate_active: bool = False,
) -> tuple[bool, list[str]]:
    """
    判断质检是否通过门槛，返回 (passed, failing_dimension_names)。

    当 auto_quality_gate=False 时：质检结果仍会推送给前端供参考，
    但不触发重写循环（始终视为通过），避免只开预警却被强制重写。

    当 ``enforce_face_slap_payoff_when_hook_required`` 为真且本章为爽点结算章
    （与 ``_calc_hook_requirement`` 注入硬约束同判）时，额外要求
    ``face_slap_payoff`` 维度分数 ≥ ``min_face_slap_payoff_score``。

    @param qc_result: quality_check 返回的完整结果 dict
    @param cfg: 生效的 writing_config dict（需含 auto_quality_gate 键）
    @param hook_mandate_active: 本章是否适用爽点硬约束（结算章/高潮期）
    @returns (True, []) 若通过；(False, [...]) 列出未达标维度名
    """
    # auto_quality_gate 关闭时：仅做信息性质检，不触发重写
    if not cfg.get("auto_quality_gate", True):
        return (True, [])

    overall = float(qc_result.get("overall_score") or 0)
    dims = qc_result.get("dimensions") or {}
    subscribe_intent = float((dims.get("subscribe_intent") or {}).get("score") or 0)

    failing: list[str] = []
    if overall < cfg["min_overall_score"]:
        failing.append(f"overall_score({overall:.1f}<{cfg['min_overall_score']})")
    if subscribe_intent < cfg["min_subscribe_intent"]:
        failing.append(f"subscribe_intent({subscribe_intent:.1f}<{cfg['min_subscribe_intent']})")

    if hook_mandate_active and cfg.get("enforce_face_slap_payoff_when_hook_required"):
        min_fs = float(cfg.get("min_face_slap_payoff_score") or 6.0)
        fs = float((dims.get("face_slap_payoff") or {}).get("score") or 0)
        if fs < min_fs:
            failing.append(f"face_slap_payoff({fs:.1f}<{min_fs}，本章为爽点结算/高潮硬约束章)")

    return (len(failing) == 0), failing


def _build_rewrite_prompt(
    qc_result: dict,
    user_prompt: str,
    strategy: str,
    attempt: int,
) -> str:
    """
    根据质检结果与重写策略，构造注入起笔 user_prompt 的修复指令块。

    策略：
      - "patch"        ：定点修复失分区域，保留通过维度的内容结构
      - "full_rewrite" ：全量重写，所有建议作为硬约束，温度更高

    @param qc_result: 上轮质检结果
    @param user_prompt: 原始用户 prompt（透传，保留作者意图）
    @param strategy: "patch" | "full_rewrite"
    @param attempt: 当前尝试轮次（第几次重写）
    @returns 拼接后的完整 user_prompt 字符串
    """
    dims = qc_result.get("dimensions") or {}
    suggestions = qc_result.get("suggestions") or []
    issues = qc_result.get("issues") or []
    overall = qc_result.get("overall_score", 0)

    # 找出失分维度（< 7 视为需要改进）
    weak_dims = [
        f"{k}（{v.get('score', '?')}分）：{v.get('comment', '')}"
        for k, v in dims.items()
        if isinstance(v, dict) and float(v.get("score") or 10) < 7
    ]

    # 找出较好维度（≥ 8 分）
    strong_dims = [k for k, v in dims.items() if isinstance(v, dict) and float(v.get("score") or 0) >= 8]

    # 按失分维度从建议列表里抽出最相关的那几条（匹配维度英文/中文关键词）
    def _pick_dim_suggestions(weak_dim_keys: list[str], all_suggestions: list[str]) -> list[str]:
        dim_keywords = {
            "plot": ["情节", "剧情", "推进"],
            "character": ["人物", "角色", "动机", "性格"],
            "setting_consistency": ["境界", "位置", "设定", "一致"],
            "pacing": ["节奏", "拖沓", "仓促"],
            "hooks": ["钩子", "悬念", "章末"],
            "outline_alignment": ["大纲", "目标"],
            "face_slap_payoff": ["打脸", "爽点", "兑现"],
            "emotional_resonance": ["情感", "揪心", "共鸣"],
            "subscribe_intent": ["追读", "订阅", "翻页"],
        }
        matched: list[str] = []
        seen_idx: set[int] = set()
        for dk in weak_dim_keys:
            for kw in dim_keywords.get(dk, [dk]):
                for i, s in enumerate(all_suggestions):
                    if i in seen_idx:
                        continue
                    if kw in s:
                        matched.append(s)
                        seen_idx.add(i)
        # 补足：失分维度相关建议不足 3 条时，按顺序补
        for i, s in enumerate(all_suggestions):
            if len(matched) >= 4:
                break
            if i not in seen_idx:
                matched.append(s)
                seen_idx.add(i)
        return matched[:4]

    if strategy == "patch":
        weak_dim_keys = [k for k, v in dims.items() if isinstance(v, dict) and float(v.get("score") or 10) < 7]
        targeted_suggestions = _pick_dim_suggestions(weak_dim_keys, suggestions)
        block = textwrap.dedent(f"""

        ===【质量门控 · 第{attempt}轮 · 定点修复 PATCH】===
        上轮整体得分：{overall}/10，未达门槛。本轮只修**失分维度**，其余结构**原样保留**。

        ▍失分维度（本轮唯一修复目标）：
        {chr(10).join(f"  • {d}" for d in weak_dims) if weak_dims else "  （无明显失分维度，仅做章末钩子强化）"}

        ▍针对失分维度的具体修复项（本轮只落实这几条，不要额外发挥）：
        {chr(10).join(f"  {i+1}. {s}" for i, s in enumerate(targeted_suggestions)) if targeted_suggestions else "  （无定向建议，按失分描述微调）"}

        ▍一致性/钩子问题：
        {chr(10).join(f"  • {iss.get('description', '')}" for iss in issues[:3]) if issues else "  （无）"}

        ▍强维度（禁止触动）：{', '.join(strong_dims) if strong_dims else '无'}
        这些维度所在段落的人物对白/场景动作/世界观细节**逐字保留或等义改写**，不要重新构思。

        PATCH 约束：
        - 修改范围控制在失分段落；强维度段落的字句结构保持稳定
        - 保持与上一轮相同的 POV、叙事节奏、人物口吻
        - 章末钩子段落若在失分维度中，必须重写；否则保留
        - 禁止在本轮引入新主线、新角色、新伏笔
        ===
        """)
    else:  # full_rewrite
        block = textwrap.dedent(f"""

        ===【质量门控 · 第{attempt}轮 · 全量重写 FULL REWRITE】===
        ⚠️ 上轮得分 {overall}/10，前几轮定点修复均未达标。
        **本轮请彻底重构本章结构**，允许推翻上一版的场景顺序、POV 切换点、章末钩子设计。

        ▍必须解决的全部问题：
        {chr(10).join(f"  • {iss.get('description', '')}" for iss in issues[:6]) if issues else "  （无具体问题，请整体重构）"}

        ▍全部编辑建议（每一条都须在正文中有对应落地）：
        {chr(10).join(f"  {i+1}. {s}" for i, s in enumerate(suggestions[:10]))}

        ▍重构硬约束：
        - 章末最后一段必须是强钩子：悬念揭开/爽感兑现/伏笔引爆——不得以角色思考或旁白收尾
        - 人物境界/位置/持有物/已习得技能必须与【情节档案】完全吻合
        - 打脸/爽点以具体场景动作落地（动作+表情+台词），不可用「众人哗然」「场面寂静」等概括词带过
        - 允许调整分场顺序与详略分布，但必须服务于本章大纲的核心事件
        - 不得扩写为两章；正文总字数控制在大纲预算 ±15% 内
        ===
        """)

    base = (user_prompt or "").strip()
    return (base + block).strip()


# ═══════════════════════════════════════════════════════════════
# 端点：gated-draft-stream（质量门控写作）
# ═══════════════════════════════════════════════════════════════

@router.post("/gated-draft-stream")
async def gated_draft_stream(
    project_id: str,
    req: GatedDraftRequest,
    db: Session = Depends(get_db),
):
    """
    质量门控写作：写稿 → 自动质检 → 未达标则重写 → 循环至通过或暂停。

    流程：
    1. 读取 project.extra.writing_config 合并请求 override_config；构建起草上下文并执行写前硬门
       （``block_on_consistency_issues`` / ``block_on_realm_mismatch``），不通过则 ``409``。
    2. 循环（最多 max_rewrite_attempts 次）：
       a. 起笔（第1轮=initial，第2轮=patch，第3轮=full_rewrite）
       b. 保存章节正文 + 创建 ChapterVersion 快照
       c. 内联质检（复用 AIService.quality_check）
       d. 检查 overall_score、subscribe_intent；若开启 ``enforce_face_slap_payoff_when_hook_required``
          且本章为爽点结算章，则额外检查 face_slap_payoff 维度
       e. 通过 → gate_passed，结束
       f. 未通过 → 生成重写 prompt，继续下一轮
    3. 全部尝试用完仍未通过 → chapter.status = needs_review，emit gate_failed

    SSE 事件见模块 docstring。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cfg = merge_writing_config(project, req.override_config)
    large_context = req.model_profile == "gemini"

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    try:
        draft_ctx = await _build_draft_context(db, project_id, chapter, project, large_context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上下文构建失败：{e}") from e

    # 空间连续性约束块：注入写章 prompt，防止 AI 跨章位置漂移
    location_context = _build_location_context(db, str(project_id))

    viol = prewrite_gate_violation(
        db, project, chapter, draft_ctx, cfg, req.consistency_issue_ack,
    )
    if viol:
        raise HTTPException(status_code=409, detail=viol)

    hook_mandate = hook_chapter_mandate_active(draft_ctx, chapter)

    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def event_stream() -> AsyncGenerator[str, None]:
        # 推送生效配置
        yield _sse({
            "event": "gate_config",
            "min_overall_score": cfg["min_overall_score"],
            "min_subscribe_intent": cfg["min_subscribe_intent"],
            "max_rewrite_attempts": cfg["max_rewrite_attempts"],
            "auto_quality_gate": cfg["auto_quality_gate"],
            "pre_write_warning_enabled": cfg["pre_write_warning_enabled"],
            "block_on_consistency_issues": cfg.get("block_on_consistency_issues", False),
            "consistency_block_severities": cfg.get("consistency_block_severities", ["high"]),
            "block_on_realm_mismatch": cfg.get("block_on_realm_mismatch", False),
            "enforce_face_slap_payoff_when_hook_required": cfg.get(
                "enforce_face_slap_payoff_when_hook_required", False
            ),
            "min_face_slap_payoff_score": cfg.get("min_face_slap_payoff_score", 6.0),
            "hook_mandate_active": hook_mandate,
        })

        user_prompt_str = (req.user_prompt or "").strip()
        last_qc: dict | None = None
        passed = False
        # 跨轮复用上下文：多轮间项目静态数据/上一章状态/承诺/伏笔/质检债务全部不变；
        # 而 gated 始终 replace_existing=True，draft_assist_stream 内部不读 existing_content。
        # 在路由层预先构建 draft_ctx，与写前硬门（一致性/境界）共用同一份上下文。

        # ── 写前预警（仅首次，pre_write_warning_enabled=True 时执行）──────────
        # 将预警结果格式化为「写前简报」块，通过 draft_assist_stream 的专属参数
        # pre_write_brief 注入（独立 2500 字预算），不拼入 user_prompt（上限 800 字）。
        # user_prompt_str 只保留用户/作者的补充指令，保持语义干净。
        # 后续重写轮仍沿用同一份 pre_warn_brief_block（状态锁定在整轮写作期间不变）。
        pre_warn_brief_block: str = ""
        if cfg["pre_write_warning_enabled"]:
            yield _sse({"event": "pre_warn_running"})
            try:
                db.refresh(chapter)
                warn_result = await _run_pre_write_warning_inline(
                    db=db, chapter=chapter, project=project,
                    project_id=project_id, svc=svc,
                )
                # 格式化为简报块，通过专属参数传入（不污染 user_prompt）
                pre_warn_brief_block = _build_pre_warn_prompt_block(warn_result)

                yield _sse({
                    "event": "pre_warn_done",
                    "ok": warn_result.get("ok", True),
                    "risk_count": warn_result.get("risk_count", 0),
                    "protagonist_fact_sheet": warn_result.get("protagonist_fact_sheet") or {},
                    "writing_brief": warn_result.get("writing_brief") or {},
                    "must_events": warn_result.get("must_events") or [],
                    "hallucination_traps": warn_result.get("hallucination_traps") or [],
                    "risks": (warn_result.get("risks") or [])[:5],
                    "reminders": (warn_result.get("reminders") or [])[:5],
                })
            except Exception as e:
                # 预警失败不阻断写作，降级为无预警模式（pre_warn_brief_block 保持空字符串）
                yield _sse({"event": "pre_warn_done", "ok": True, "risk_count": 0,
                            "error": f"写前预警失败（已降级继续写作）：{e}"})

        for attempt in range(1, cfg["max_rewrite_attempts"] + 1):
            # ── 决定本轮策略 ───────────────────────────────────────────
            if attempt == 1:
                strategy = "initial"
            elif attempt == cfg["max_rewrite_attempts"]:
                strategy = "full_rewrite"
            else:
                strategy = "patch"

            # ── 若是重写轮，先把上轮 QC 建议注入 prompt ───────────────
            current_user_prompt = user_prompt_str
            if attempt > 1 and last_qc is not None:
                current_user_prompt = _build_rewrite_prompt(
                    qc_result=last_qc,
                    user_prompt=user_prompt_str,
                    strategy=strategy,
                    attempt=attempt,
                )

            yield _sse({
                "event": "attempt_start",
                "attempt": attempt,
                "max_attempts": cfg["max_rewrite_attempts"],
                "strategy": strategy,
            })

            # ── 刷新章节实体（保存正文用，仍每轮做）；上下文复用路由层预构建的 draft_ctx ──
            db.refresh(chapter)

            accumulated = ""
            try:
                async for chunk in svc.draft_assist_stream(
                    **draft_ctx,
                    user_prompt=current_user_prompt,
                    # 写前简报走独立通道（2500 字预算），不与 user_prompt 竞争截断配额；
                    # 重写轮沿用首轮生成的同一份简报，保持状态锁定在整轮写作期间一致。
                    pre_write_brief=pre_warn_brief_block,
                    # 空间连续性约束：各章复用同一份（角色位置在整轮写作期间不变）
                    location_context=location_context,
                    replace_existing=True,  # 门控写作始终整章重写
                    stream_log_context={
                        "project_id": str(project_id),
                        "chapter_id": str(req.chapter_id),
                        "gated_attempt": attempt,
                    },
                ):
                    accumulated += chunk
                    yield _sse({"text": chunk})
            except Exception as e:
                yield _sse({"error": f"起笔失败（第{attempt}轮）：{e}"})
                return

            # P2.5: 推送本轮截断警告（如有）
            attempt_warnings = getattr(svc, "_truncation_warnings", None) or []
            if attempt_warnings:
                yield _sse({
                    "event": "truncation_warning",
                    "attempt": attempt,
                    "warnings": list(attempt_warnings),
                })

            # 提取叙事正文（去掉索引块）
            narr, _ = split_plain_manuscript_and_index_block(accumulated)
            draft_body = narr.strip() if narr.strip() else accumulated.strip()
            if not draft_body:
                yield _sse({"error": f"第{attempt}轮未收到正文内容"})
                return

            word_count = _count_words_plain(draft_body)
            yield _sse({"event": "attempt_done", "attempt": attempt, "words": word_count})

            # ── 保存到 DB + 创建 ChapterVersion ───────────────────────
            try:
                _save_chapter_content(db, chapter, draft_body, attempt)
                db.refresh(chapter)
            except Exception as e:
                yield _sse({"error": f"保存失败（第{attempt}轮）：{e}"})
                return

            # ── 内联质检 ──────────────────────────────────────────────
            yield _sse({"event": "qc_running", "attempt": attempt})
            try:
                qc = await _run_quality_check_inline(
                    db=db,
                    chapter=chapter,
                    project=project,
                    project_id=project_id,
                    large_context=large_context,
                    svc=svc,
                )
                last_qc = qc
            except Exception as e:
                yield _sse({"error": f"质检失败（第{attempt}轮）：{e}"})
                return

            overall_score = float(qc.get("overall_score") or 0)
            dims = qc.get("dimensions") or {}
            subscribe_intent_score = float(
                (dims.get("subscribe_intent") or {}).get("score") or 0
            )

            yield _sse({
                "event": "qc_result",
                "attempt": attempt,
                "overall_score": overall_score,
                "subscribe_intent": subscribe_intent_score,
                "passed": False,  # 先假设未通过，后面覆写
                "dimensions": {
                    k: {
                        "score": v.get("score"),
                        "status": v.get("status"),
                        "comment": v.get("comment", ""),
                    }
                    for k, v in dims.items()
                    if isinstance(v, dict)
                },
                "suggestions": (qc.get("suggestions") or [])[:5],
                "summary": qc.get("summary", ""),
            })

            # ── 判断是否通过 ───────────────────────────────────────────
            ok, failing = _check_passed(qc, cfg, hook_mandate_active=hook_mandate)
            if ok:
                passed = True
                # 覆写最后一个 qc_result 中的 passed=False → 补发 gate_passed
                yield _sse({
                    "event": "gate_passed",
                    "attempt": attempt,
                    "overall_score": overall_score,
                    "subscribe_intent": subscribe_intent_score,
                })
                # 更新章节状态为 done
                chapter.status = "done"
                db.commit()
                break

            # ── 未通过，若还有机会则推进下一轮 ───────────────────────
            if attempt < cfg["max_rewrite_attempts"]:
                next_strategy = "full_rewrite" if attempt + 1 == cfg["max_rewrite_attempts"] else "patch"
                yield _sse({
                    "event": "rewrite_queued",
                    "attempt": attempt,
                    "next_attempt": attempt + 1,
                    "strategy": next_strategy,
                    "failing_dimensions": failing,
                    "overall_score": overall_score,
                    "subscribe_intent": subscribe_intent_score,
                })

        # ── 全部尝试耗尽 ───────────────────────────────────────────────
        if not passed:
            final_score = float((last_qc or {}).get("overall_score") or 0)
            final_subscribe = float(
                ((last_qc or {}).get("dimensions") or {})
                .get("subscribe_intent", {})
                .get("score") or 0
            )
            chapter.status = "needs_review"
            db.commit()
            yield _sse({
                "event": "gate_failed",
                "max_attempts": cfg["max_rewrite_attempts"],
                "final_score": final_score,
                "final_subscribe_intent": final_subscribe,
                "min_overall_score": cfg["min_overall_score"],
                "min_subscribe_intent": cfg["min_subscribe_intent"],
                "message": (
                    f"经过 {cfg['max_rewrite_attempts']} 次尝试仍未达标"
                    f"（综合分 {final_score:.1f}/{cfg['min_overall_score']}，"
                    f"订阅意愿 {final_subscribe:.1f}/{cfg['min_subscribe_intent']}），"
                    "章节已暂停，请人工审阅后决定下一步。"
                ),
            })

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
