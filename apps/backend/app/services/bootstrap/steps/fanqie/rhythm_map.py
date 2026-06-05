"""Bootstrap Fanqie Steps 15-16：爽点节奏图 + 剧情储量池。

爽点节奏图：前50章每章打标（大爽/小爽/推进/过渡），连续过渡超3章自动标红。
剧情储量池：预备 3-5 个可插入的自洽支线弧，供主线卡壳或冲字数时调用。

重构说明（2026-06）
------------------
chapter_tags 改为规则生成（从 face_slap_map + golden_finger 的已知锚点推算），
LLM 只负责生成 story_buffer（3-5个备用支线弧），节省约1次完整 LLM 调用。

规则逻辑：
- 打脸对象的 chapter_estimate → big_win
- 金手指 upgrade_stages 的 chapter_range 起始章 → big_win
- 每3章一个 small_win（无大爽点的区间）
- 其余为 progress；transition 只由 repair_rhythm_tags 必要时注入

产物写入 Project.extra['rhythm_map']。
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.models import Project
from app.services.bootstrap.json_once import BootstrapStepError
from app.services.bootstrap.steps.fanqie._json_once import call_fanqie_json_once
from app.services.llm_errors import is_retryable_llm_error

logger = logging.getLogger(__name__)

_STEP = "rhythm_map"

_SLAP_TO_SATISFACTION = {
    "财富碾压": "财富碾压",
    "武力碾压": "武力展示",
    "身份碾压": "势力扩张",
    "感情反转": "感情线",
    "当众揭穿": "悬疑揭秘",
}
_FALLBACK_SATISFACTIONS = ("武力展示", "财富碾压", "感情线", "悬疑揭秘", "势力扩张")

# ──────────────────────────────────────────────────────
# 规则生成 chapter_tags（无 LLM）
# ──────────────────────────────────────────────────────

def _extract_ch(s: str) -> int | None:
    """从 '约第3章' / '第3-5章' / '3' 等字符串提取首个章节号。"""
    m = re.search(r"\d+", str(s))
    return int(m.group()) if m else None


def _build_chapter_tags_by_rule(ctx: dict, total: int = 50) -> list[dict]:
    """
    从已有锚点规则推导前 `total` 章爽点标注，不调用 LLM。

    Args:
        ctx:   bootstrap 上下文（需要 face_slap_map / golden_finger）。
        total: 生成章节数，默认 50。

    Returns:
        chapter_tags 列表，格式与原 LLM 产物相同。
    """
    fsm = ctx.get("face_slap_map") or {}
    gf = ctx.get("golden_finger") or {}

    # 收集大爽点章节（打脸 + 金手指升级）
    big_win_chapters: dict[int, str] = {}

    first_slap = fsm.get("first_slap_chapter")
    if isinstance(first_slap, int) and 1 <= first_slap <= total:
        big_win_chapters[first_slap] = "首次打脸"

    for target in (fsm.get("targets") or []):
        ch = _extract_ch(str(target.get("chapter_estimate", "")))
        if ch and 1 <= ch <= total:
            name = (target.get("name") or "打脸对象")[:10]
            big_win_chapters[ch] = f"打脸·{name}"

    for stage in (gf.get("upgrade_stages") or []):
        ch = _extract_ch(str(stage.get("chapter_range", "")))
        if ch and 1 <= ch <= total:
            stage_name = (stage.get("name") or f"阶段{stage.get('stage', '')}")[:8]
            big_win_chapters[ch] = f"升级·{stage_name}"

    # 构建基础标注（先全部设为 progress）
    tags: list[dict] = [{"ch": i, "type": "progress", "note": ""} for i in range(1, total + 1)]

    # 标注大爽点
    for ch, note in big_win_chapters.items():
        tags[ch - 1]["type"] = "big_win"
        tags[ch - 1]["note"] = note

    # 每3章补一个 small_win（若该章还是 progress）
    # 从第2章开始，每3章一个小爽点，确保读者不断获得正反馈
    for i in range(1, total, 3):  # i = 1, 4, 7, 10, ...（0-based index）
        if tags[i]["type"] == "progress":
            tags[i]["type"] = "small_win"
            tags[i]["note"] = "小胜利"

    # 第1章固定为 progress（建立处境）
    if tags[0]["type"] == "small_win":
        tags[0]["type"] = "progress"
        tags[0]["note"] = "开局建立处境"

    return tags


def _compute_major_payoffs(tags: list[dict]) -> list[int]:
    """从 chapter_tags 中提取最重要的5个大爽点章节号。"""
    big_wins = [t["ch"] for t in tags if t.get("type") == "big_win"]
    # 均匀选5个，保留首末
    if len(big_wins) <= 5:
        return sorted(big_wins)
    step = max(1, len(big_wins) // 4)
    indices = [0, step, 2 * step, 3 * step, len(big_wins) - 1]
    return sorted({big_wins[i] for i in indices})


def _build_story_buffer_by_rule(ctx: dict) -> list[dict]:
    """从打脸地图 / 金手指锚点推导备用支线弧，网关不可用时兜底。"""
    fsm = ctx.get("face_slap_map") or {}
    gf = ctx.get("golden_finger") or {}
    buffers: list[dict] = []

    for i, target in enumerate((fsm.get("targets") or [])[:5]):
        name = (target.get("name") or f"支线{i + 1}")[:5]
        ch = _extract_ch(str(target.get("chapter_estimate", "")))
        start = max(1, (ch or (i + 1) * 10) - 5)
        end = ch or (i + 1) * 10 + 5
        slap_type = str(target.get("slap_type") or "")
        satisfaction = _SLAP_TO_SATISFACTION.get(slap_type) or _FALLBACK_SATISFACTIONS[i % len(_FALLBACK_SATISFACTIONS)]
        scene = (target.get("slap_scene") or target.get("initial_attitude") or "支线矛盾激化")[:40]
        buffers.append({
            "name": name,
            "chapter_count": 10 + (i % 3) * 3,
            "trigger_condition": "主线推进过快、需要拖字数或给读者喘息时插入",
            "core_conflict": scene,
            "satisfaction_type": satisfaction,
            "insertion_point": f"第{start}-{end}章之间",
        })

    stages = gf.get("upgrade_stages") or []
    if len(buffers) < 3 and stages:
        for i, stage in enumerate(stages[: 3 - len(buffers)]):
            ch = _extract_ch(str(stage.get("chapter_range", "")))
            stage_name = (stage.get("name") or f"阶段{i + 1}")[:5]
            start = max(1, (ch or 15) - 3)
            end = (ch or 20) + 5
            buffers.append({
                "name": stage_name,
                "chapter_count": 12,
                "trigger_condition": "金手指升级前需要铺垫或缓冲节奏",
                "core_conflict": f"围绕{stage_name}的能力试炼与阻碍",
                "satisfaction_type": _FALLBACK_SATISFACTIONS[(len(buffers) + i) % len(_FALLBACK_SATISFACTIONS)],
                "insertion_point": f"第{start}-{end}章之间",
            })

    if len(buffers) < 3:
        for i in range(3 - len(buffers)):
            buffers.append({
                "name": f"缓冲弧{i + 1}",
                "chapter_count": 10,
                "trigger_condition": "主线卡壳或节奏过快时插入",
                "core_conflict": "支线势力试探主角底线",
                "satisfaction_type": _FALLBACK_SATISFACTIONS[i % len(_FALLBACK_SATISFACTIONS)],
                "insertion_point": f"第{(i + 2) * 12}-{(i + 2) * 12 + 8}章之间",
            })

    return buffers[:5]


async def _load_story_buffer(
    svc: Any,
    *,
    system: str,
    prompt: str,
    validate,
    ctx: dict,
) -> tuple[list[dict], str, str | None]:
    """尝试 LLM 生成 story_buffer；瞬时网关错误时回退规则模板。"""
    try:
        buffer_data = await call_fanqie_json_once(
            svc,
            step=_STEP,
            system=system,
            prompt=prompt,
            task="bootstrap.opening_contract",
            validate=validate,
        )
        return buffer_data.get("story_buffer") or [], "llm", None
    except BootstrapStepError:
        raise
    except Exception as exc:
        if not is_retryable_llm_error(exc):
            raise
        fallback = _build_story_buffer_by_rule(ctx)
        logger.warning(
            "rhythm_map story_buffer LLM failed (%s), using rule fallback (%d arcs)",
            exc,
            len(fallback),
        )
        return fallback, "rule_fallback", str(exc)


# ──────────────────────────────────────────────────────
# LLM 只生成 story_buffer（网关失败时规则兜底）
# ──────────────────────────────────────────────────────

async def gen_rhythm_map(svc: Any, project: Project, ctx: dict) -> dict:
    """
    生成爽点节奏图（前50章，规则推导）+ 剧情储量池（3-5个备用弧，LLM生成）。

    chapter_tags 由规则计算，story_buffer 由 LLM 生成，节省约1次完整 LLM 调用。

    @returns rhythm_map dict；包含 chapter_tags 列表和 story_buffer 列表
    """
    from app.services.bootstrap.rhythm_pacing import (
        detect_dry_spells,
        repair_rhythm_tags,
    )

    fanqie_pos = ctx.get("fanqie_positioning") or {}
    fsm = ctx.get("face_slap_map") or {}
    gf = ctx.get("golden_finger") or {}

    # ── Step 1：规则生成 chapter_tags（无 LLM）────────────
    raw_tags = _build_chapter_tags_by_rule(ctx, total=50)
    repaired, repair_notes = repair_rhythm_tags(raw_tags)
    chapter_tags = repaired or raw_tags
    auto_dry_spells = detect_dry_spells(chapter_tags)
    major_payoffs = _compute_major_payoffs(chapter_tags)

    # ── Step 2：LLM 只生成 story_buffer ──────────────────
    system = "你是番茄小说节奏规划专家，只返回 JSON，不要解释文字。"

    slap_rhythm = fsm.get("slap_rhythm", "每3章一小打，每10章一大打")
    stages = gf.get("upgrade_stages") or []

    prompt = f"""小说：《{ctx['project_title']}》
类型公式：{fanqie_pos.get('genre_archetype', '')}
核心爽感：{fanqie_pos.get('core_satisfaction', '')}
打脸节奏：{slap_rhythm}
金手指阶段数：{len(stages)}个
打脸升级路径：{fsm.get('escalation_path', '')}

为本书设计3-5个「剧情储量池」备用支线弧（主线推进过快或卡壳时插入）。

返回 JSON：
{{
  "story_buffer": [
    {{
      "name": "支线弧名称（5字内）",
      "chapter_count": 15,
      "trigger_condition": "什么情况下插入（主线推进过快/需要拖字数/给读者喘息）",
      "core_conflict": "支线核心矛盾（一句话）",
      "satisfaction_type": "爽感类型（武力展示/财富碾压/感情线/悬疑揭秘）",
      "insertion_point": "建议插入位置（如：第15-20章之间）"
    }},
    {{"name": "...", "chapter_count": 10, "trigger_condition": "...", "core_conflict": "...", "satisfaction_type": "...", "insertion_point": "..."}},
    {{"name": "...", "chapter_count": 12, "trigger_condition": "...", "core_conflict": "...", "satisfaction_type": "...", "insertion_point": "..."}}
  ]
}}

要求：
1. story_buffer 必须有3-5个弧线，每个都能独立成章
2. 至少覆盖2种不同的爽感类型
3. 只返回 JSON"""

    def _validate(data: Any) -> str | None:
        if not isinstance(data, dict):
            return "须为 JSON 对象"
        buf = data.get("story_buffer")
        if not isinstance(buf, list) or len(buf) < 2:
            return "story_buffer 至少需要2个支线弧"
        return None

    story_buffer, buffer_source, buffer_fallback_error = await _load_story_buffer(
        svc,
        system=system,
        prompt=prompt,
        validate=_validate,
        ctx=ctx,
    )

    # ── 合并产物 ──────────────────────────────────────────
    generated_by = "rule+llm" if buffer_source == "llm" else "rule+rule_fallback"
    data: dict = {
        "chapter_tags": chapter_tags,
        "story_buffer": story_buffer,
        "major_payoff_chapters": major_payoffs,
        "dry_spell_warnings": [f"连续过渡区间：{ds}" for ds in auto_dry_spells] if auto_dry_spells else [],
        "auto_dry_spells": auto_dry_spells,
        "_generated_by": generated_by,
        "_story_buffer_source": buffer_source,
    }
    if buffer_fallback_error:
        data["story_buffer_fallback_reason"] = buffer_fallback_error
    if repair_notes:
        data["rhythm_repair_notes"] = repair_notes

    extra = dict(project.extra or {})
    extra["rhythm_map"] = data
    project.extra = extra
    svc.db.commit()
    ctx["rhythm_map"] = data

    from app.services.bootstrap.fanqie_normalize import converge_fanqie_project

    converge_fanqie_project(svc.db, project, ctx)
    return data


