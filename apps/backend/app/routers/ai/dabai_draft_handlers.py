"""dabai 写章路由编排 — draft-assist / gated-draft 共用。"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from sqlalchemy.orm import Session

from app.models import Chapter, Project
from app.routers.ai.gated_draft_helpers import _count_words_plain, _save_chapter_content
from app.services.ai.service import AIService
from app.services.dabai.draft_stream import stream_dabai_chapter_draft
from app.services.dabai.outline_plan import resolve_chapter_plan
from app.services.dabai.quality_check import run_dabai_quality
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block
from app.utils.dabai_mode import is_dabai_project


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def dabai_draft_assist_event_stream(
    db: Session,
    svc: AIService,
    project: Project,
    chapter: Chapter,
    project_id: str,
    *,
    user_prompt: str,
    replace_existing: bool,
    stream_log_ctx: dict,
) -> AsyncGenerator[str, None]:
    """普通起笔/重写 SSE（与 draft-assist 格式兼容：``{text}`` chunk）。"""
    yield _sse({
        "event": "dabai_draft_mode",
        "message": "大白文专线：按章节要素五拍写正文",
    })
    try:
        async for chunk in stream_dabai_chapter_draft(
            svc,
            db,
            project,
            chapter,
            project_id=project_id,
            user_prompt=user_prompt,
            replace_existing=replace_existing,
            stream_log_context=stream_log_ctx,
        ):
            yield _sse({"text": chunk})
    except Exception as e:
        yield _sse({"error": str(e)})
        return
    warnings = getattr(svc, "_truncation_warnings", None) or []
    if warnings:
        yield _sse({"event": "truncation_warning", "warnings": list(warnings)})
    yield "data: [DONE]\n\n"


async def dabai_gated_draft_event_stream(
    db: Session,
    svc: AIService,
    project: Project,
    chapter: Chapter,
    project_id: str,
    *,
    user_prompt: str,
    stream_log_ctx: dict,
) -> AsyncGenerator[str, None]:
    """dabai 门控写章：单次按章节要素起笔 + 设定一致性校验（不做文采质检循环）。"""
    yield _sse({
        "event": "gate_config",
        "dabai_mode": True,
        "min_overall_score": 0,
        "min_subscribe_intent": 0,
        "max_rewrite_attempts": 1,
        "auto_quality_gate": False,
        "pre_write_warning_enabled": False,
        "message": "大白文专线：跳过通用质检循环，写后做设定一致性校验",
    })
    yield _sse({"event": "attempt_start", "attempt": 1, "max_attempts": 1, "strategy": "initial"})

    accumulated = ""
    try:
        async for chunk in stream_dabai_chapter_draft(
            svc,
            db,
            project,
            chapter,
            project_id=project_id,
            user_prompt=user_prompt,
            replace_existing=True,
            stream_log_context={**stream_log_ctx, "gated_attempt": 1},
        ):
            accumulated += chunk
            yield _sse({"text": chunk})
    except Exception as e:
        yield _sse({"error": f"起笔失败：{e}"})
        return

    narr, _ = split_plain_manuscript_and_index_block(accumulated)
    draft_body = narr.strip() if narr.strip() else accumulated.strip()
    if not draft_body:
        yield _sse({"error": "未收到正文内容"})
        return

    word_count = _count_words_plain(draft_body)
    yield _sse({"event": "attempt_done", "attempt": 1, "words": word_count})

    try:
        _save_chapter_content(db, chapter, draft_body, attempt=1)
        db.refresh(chapter)
    except Exception as e:
        yield _sse({"error": f"保存失败：{e}"})
        return

    yield _sse({
        "event": "qc_running", "attempt": 1, "dabai_consistency": True,
        "label": "dabai 质检 v2：设定一致性 + 衔接/五拍/钩子…",
    })
    plan = resolve_chapter_plan(db, project_id, chapter)
    report = await run_dabai_quality(svc, db, project, chapter, plan_node=plan)
    chapter.last_quality_report = report
    chapter.last_quality_score = report.get("overall_score")
    passed = bool(report.get("consistency_pass", True))
    blockers = report.get("blockers") or []
    warnings = report.get("warnings") or []
    llm_part = report.get("llm") or {}

    score = float(report.get("overall_score") or (100 if passed else 40))

    yield _sse({
        "event": "qc_result",
        "attempt": 1,
        "dabai_consistency": True,
        "passed": passed,
        "overall_score": score,
        "subscribe_intent": score,
        "blockers": blockers[:5],
        "warnings": warnings[:8],
        "continuity_score": llm_part.get("continuity_score"),
        "beat_score": llm_part.get("beat_score"),
        "hook_score": llm_part.get("hook_score"),
        "suggestions": llm_part.get("suggestions") or [],
        "summary": (
            "质检通过" if passed and not warnings
            else f"{len(warnings)} 条提醒" if passed
            else f"存在 {len(blockers)} 条阻断项"
        ),
    })

    if passed:
        chapter.status = "done"
        db.commit()
        yield _sse({
            "event": "gate_passed",
            "attempt": 1,
            "dabai_consistency": True,
            "word_count": word_count,
            "overall_score": score,
            "subscribe_intent": score,
        })
    else:
        chapter.status = "needs_review"
        db.commit()
        yield _sse({
            "event": "gate_failed",
            "attempt": 1,
            "reason": "dabai_consistency",
            "blockers": blockers[:5],
            "final_score": score,
            "final_subscribe_intent": score,
        })

    yield "data: [DONE]\n\n"


def should_route_dabai_draft(project: Project | None) -> bool:
    return is_dabai_project(project)
