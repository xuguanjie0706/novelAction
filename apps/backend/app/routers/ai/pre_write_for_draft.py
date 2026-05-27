"""
写前预警 → 正文 prompt 注入（普通起笔与门控起笔共用）。

设计动机：预警的首要消费者是写章模型，而非侧栏展示；普通 draft-assist/stream
在开启 pre_write_warning_enabled 时也必须注入 pre_write_brief。

「重写本章」（replace_existing=True）时若本章已有落库的预警记录，则跳过主编审稿 LLM，
直接复用历史 result 组装 pre_write_brief，避免重复耗时与简报漂移。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Chapter, PreWriteWarningRecord, Project
from app.services.ai_service import AIService

# 复用路径：简报块除去固定标题后至少需有实质内容
_MIN_REUSED_BRIEF_CHARS = 80


def _pre_warn_done_payload(
    warn_result: dict,
    *,
    record_id: str | None,
    reused: bool = False,
) -> dict[str, Any]:
    """构造 pre_warn_done SSE 载荷（新生成与复用共用字段）。"""
    return {
        "event": "pre_warn_done",
        "ok": warn_result.get("ok", True),
        "risk_count": warn_result.get("risk_count", 0),
        "protagonist_fact_sheet": warn_result.get("protagonist_fact_sheet") or {},
        "writing_brief": warn_result.get("writing_brief") or {},
        "must_events": warn_result.get("must_events") or [],
        "hallucination_traps": warn_result.get("hallucination_traps") or [],
        "risks": (warn_result.get("risks") or [])[:5],
        "reminders": (warn_result.get("reminders") or [])[:5],
        "rag_retrieval_log_id": warn_result.get("rag_retrieval_log_id"),
        "record_id": record_id,
        "reused": reused,
    }


def try_reuse_pre_write_brief_from_record(
    db: Session,
    *,
    project_id: str,
    chapter_id: str,
) -> tuple[str, dict[str, Any]] | None:
    """
    若本章存在可复用的写前预警落库记录，返回 (brief_block, pre_warn_done_event)。

    供单元测试与 resolve_pre_write_brief_for_draft 共用；无可用记录时返回 None。
    """
    from app.routers.ai.gated_draft_helpers import _build_pre_warn_prompt_block

    rec = (
        db.query(PreWriteWarningRecord)
        .filter(
            PreWriteWarningRecord.project_id == project_id,
            PreWriteWarningRecord.chapter_id == chapter_id,
        )
        .order_by(PreWriteWarningRecord.created_at.desc())
        .first()
    )
    if not rec:
        return None
    raw = rec.result
    warn_result = raw if isinstance(raw, dict) else {}
    brief = _build_pre_warn_prompt_block(warn_result).strip()
    if len(brief) < _MIN_REUSED_BRIEF_CHARS:
        return None
    return brief, _pre_warn_done_payload(
        warn_result,
        record_id=str(rec.id),
        reused=True,
    )


def _append_storyline_pre_warn_events(
    db: Session,
    *,
    project_id: str,
    chapter: Chapter,
    events: list[dict[str, Any]],
) -> None:
    """在写前预警流中追加故事线织网 SSE（与主编审稿并行，纯 DB）。"""
    from app.services.ai.storyline_pre_warn import compute_storyline_pre_warn_events

    ch_no = chapter.sort_order or 0
    outline_nid = str(chapter.outline_node_id) if chapter.outline_node_id else None
    sl_events = compute_storyline_pre_warn_events(
        db,
        project_id,
        ch_no,
        outline_node_id=outline_nid,
    )
    events.extend(sl_events)


async def resolve_pre_write_brief_for_draft(
    db: Session,
    *,
    chapter: Chapter,
    project: Project,
    project_id: str,
    svc: AIService,
    enabled: bool,
    model_profile: str,
    llm_provider_id: str | None,
    persist_record: bool = True,
    reuse_if_exists: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    """
    若开启写前预警，执行主编审稿并格式化为 draft_assist_stream 的 pre_write_brief。

    Args:
        reuse_if_exists: 为 True 时（通常伴随整章重写），若本章已有预警落库则跳过 LLM 审稿并复用。

    Returns:
        (brief_block, side_events) — side_events 为 SSE JSON 载荷列表（pre_warn_* / rag_context）
    """
    if not enabled:
        return "", []

    # 延迟导入，避免 gated_draft_routes ↔ draft_routes 循环依赖（实现已迁至 helpers）
    from app.routers.ai.gated_draft_helpers import (
        _build_pre_warn_prompt_block,
        _persist_pre_write_warning_record,
        _run_pre_write_warning_inline,
    )

    if reuse_if_exists:
        reused = try_reuse_pre_write_brief_from_record(
            db,
            project_id=project_id,
            chapter_id=str(chapter.id),
        )
        if reused is not None:
            brief, done_evt = reused
            events: list[dict[str, Any]] = [done_evt]
            _append_storyline_pre_warn_events(
                db, project_id=project_id, chapter=chapter, events=events,
            )
            return brief, events

    events: list[dict[str, Any]] = [{"event": "pre_warn_running"}]
    try:
        warn_result, warn_plan_summary = await _run_pre_write_warning_inline(
            db=db,
            chapter=chapter,
            project=project,
            project_id=project_id,
            svc=svc,
        )
        rag_ctx = warn_result.get("rag_context")
        if isinstance(rag_ctx, dict) and rag_ctx.get("event") == "rag_context":
            events.append(rag_ctx)

        brief = _build_pre_warn_prompt_block(warn_result)
        record_id: str | None = None
        if persist_record:
            rec = _persist_pre_write_warning_record(
                db,
                project=project,
                chapter=chapter,
                chapter_plan_summary=warn_plan_summary,
                model_profile=model_profile or "local",
                llm_provider_id=llm_provider_id,
                result=warn_result,
            )
            record_id = str(rec.id)

        events.append(_pre_warn_done_payload(warn_result, record_id=record_id, reused=False))
        _append_storyline_pre_warn_events(
            db, project_id=project_id, chapter=chapter, events=events,
        )
        return brief, events
    except Exception as exc:
        events.append({
            "event": "pre_warn_done",
            "ok": True,
            "risk_count": 0,
            "error": f"写前预警失败（已降级继续写作）：{exc}",
        })
        return "", events
