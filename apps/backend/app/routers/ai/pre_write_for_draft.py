"""
写前预警 → 正文 prompt 注入（普通起笔与门控起笔共用）。

设计动机：预警的首要消费者是写章模型，而非侧栏展示；普通 draft-assist/stream
在开启 pre_write_warning_enabled 时也必须注入 pre_write_brief。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Chapter, Project
from app.services.ai_service import AIService


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
) -> tuple[str, list[dict[str, Any]]]:
    """
  若开启写前预警，执行主编审稿并格式化为 draft_assist_stream 的 pre_write_brief。

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

        events.append({
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
        })
        return brief, events
    except Exception as exc:
        events.append({
            "event": "pre_warn_done",
            "ok": True,
            "risk_count": 0,
            "error": f"写前预警失败（已降级继续写作）：{exc}",
        })
        return "", events
