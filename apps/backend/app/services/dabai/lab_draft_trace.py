"""dabai 实验书架正文写作 trace — 结构化日志，便于排查衔接/注入冲突。

落点：
- ``logger`` INFO 行（grep ``dabai_lab_draft_trace``）；
- ``llm_call_logs.context``（task=dabai.write 时由路由传入）。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.services.dabai.lab_draft_context import LabDraftContext
from app.services.dabai.lab_prompt_shared import has_location_gap, needs_location_bridge

logger = logging.getLogger("dabai.lab_draft_trace")

_TRACE_VERSION = "dabai-lab-draft-trace-v1"


def _preview(text: str, n: int = 120) -> str:
    t = (text or "").strip().replace("\n", " ")
    return t[:n] + ("…" if len(t) > n else "")


def build_lab_draft_trace(
    *,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    ctx: LabDraftContext,
    prev_ch: DabaiChapterOutline | None,
    location_bridge_block: str,
    pre_warn_result: dict | None,
    scene_block: str,
    replace_existing: bool,
    rerun_pre_warn: bool,
    rerun_scene_plan: bool,
    user_instruction: str = "",
    beat_source: str | None = None,
    yaqu_similarity: float | None = None,
    opening_policy_mode: str | None = None,
) -> dict[str, Any]:
    """组装写章 trace 字典（不写库，供日志与 llm_call_logs.context）。"""
    prev_loc = (prev_ch.location or "").strip() if prev_ch else ""
    curr_loc = (ch.location or "").strip()
    outline_gap = bool(prev_ch and has_location_gap(prev_loc, curr_loc))
    bridge_needed = bool(
        prev_ch and needs_location_bridge(prev_ch, ch, ctx.prev_tail),
    )
    opening_directive = ""
    if pre_warn_result:
        opening_directive = str(pre_warn_result.get("opening_directive") or "")

    trace: dict[str, Any] = {
        "trace_version": _TRACE_VERSION,
        "dabai_project_id": str(project.id),
        "dabai_chapter_id": str(ch.id),
        "dabai_chapter_number": ch.chapter_number,
        "replace_existing": replace_existing,
        "rerun_pre_warn": rerun_pre_warn,
        "rerun_scene_plan": rerun_scene_plan,
        "has_user_instruction": bool((user_instruction or "").strip()),
        "blocks": {
            "prev_tail_len": len(ctx.prev_tail or ""),
            "prev_tail_preview": _preview(ctx.prev_tail, 160),
            "prev_full": bool(ctx.prev_full_block.strip()),
            "prev_full_len": len(ctx.prev_full_block or ""),
            "prev_hook": bool(ctx.prev_hook_block.strip()),
            "recent_plot": bool(ctx.recent_plot_block.strip()),
            "memory": bool(ctx.memory_block.strip()),
            "clue": bool(ctx.clue_block.strip()),
            "panel": bool(ctx.panel_block.strip()),
            "pre_warn": bool(pre_warn_result),
            "scene_plan": bool(scene_block.strip()),
            "location_bridge": bool(location_bridge_block.strip()),
        },
        "continuity": {
            "prev_outline_location": prev_loc,
            "curr_outline_location": curr_loc,
            "outline_location_gap": outline_gap,
            "location_bridge_needed": bridge_needed,
            "location_bridge_injected": bool(location_bridge_block.strip()),
            "prev_tail_at_curr_scene": outline_gap and not bridge_needed,
            "opening_directive_preview": _preview(opening_directive, 160),
        },
    }
    if beat_source is not None:
        trace["beat_source"] = beat_source
    if yaqu_similarity is not None:
        trace["yaqu_similarity"] = yaqu_similarity
    if opening_policy_mode is not None:
        trace["opening_policy_mode"] = opening_policy_mode
    return trace


def log_lab_draft_trace(trace: dict[str, Any], *, phase: str) -> None:
    """输出结构化 trace（phase=assembly|done）。"""
    payload = {"phase": phase, **trace}
    logger.info("dabai_lab_draft_trace %s", json.dumps(payload, ensure_ascii=False))


def llm_call_context_from_trace(trace: dict[str, Any]) -> dict[str, Any]:
    """供 ``AIService._stream_ai(context=...)`` 写入 llm_call_logs。"""
    return {
        "dabai_project_id": trace.get("dabai_project_id"),
        "dabai_chapter_id": trace.get("dabai_chapter_id"),
        "dabai_chapter_number": trace.get("dabai_chapter_number"),
        "replace_existing": trace.get("replace_existing"),
        "draft_trace": trace,
    }
