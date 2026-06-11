"""dabai 实验书架写后流水线 — 质检 + 复盘后台任务（抗断流）。

独立 SessionLocal 跑在 asyncio task 里：客户端关页只丢进度展示，
落库照常完成。进度 dict 经 Queue 转发，None 哨兵收尾；
单步失败 put 带 error 的 done 事件，绝不抛出中断。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import UUID

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.services.dabai.lab_debrief import run_lab_debrief
from app.services.dabai.lab_quality import run_lab_quality

logger = logging.getLogger(__name__)

# 强引用集合：防止 create_task 后无引用被 GC（asyncio 官方告诫）。
_POST_WRITE_TASKS: set[asyncio.Task] = set()


async def _run_post_write_pipeline(
    project_id: UUID,
    chapter_id: UUID,
    *,
    model_profile: str,
    llm_provider_id: Optional[UUID],
    user_id,
    events: asyncio.Queue,
) -> None:
    """写后自动质检 + 复盘。"""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        project = db.query(DabaiProject).filter(DabaiProject.id == project_id).first()
        ch = (
            db.query(DabaiChapterOutline)
            .filter(DabaiChapterOutline.id == chapter_id)
            .first()
        )
        if not project or not ch:
            return
        from app.services.ai.service import AIService
        ai = AIService(profile=model_profile, db=db,
                       llm_provider_id=llm_provider_id, user_id=user_id)

        events.put_nowait({"event": "quality_running", "dabai_mode": True})
        try:
            report = await run_lab_quality(ai, db, project, ch, with_llm=True)
            events.put_nowait({"event": "quality_done", "ok": True,
                               "status": report.get("status"),
                               "overall_score": report.get("overall_score"),
                               "llm_status": report.get("llm_status")})
        except Exception as exc:  # noqa: BLE001
            logger.warning("dabai-lab 写后质检失败 chapter=%s：%s", chapter_id, exc)
            db.rollback()
            events.put_nowait({"event": "quality_done", "ok": False, "error": str(exc)})

        events.put_nowait({"event": "debrief_running", "dabai_mode": True})
        try:
            result = await run_lab_debrief(ai, db, project, ch)
            events.put_nowait({"event": "debrief_done", "ok": True,
                               "summary": result.get("summary"),
                               "memory_count": result.get("memory_count"),
                               "new_clues": result.get("new_clues"),
                               "resolved_clues": result.get("resolved_clues"),
                               "asset_changes": result.get("asset_changes"),
                               "relation_changes": result.get("relation_changes")})
        except Exception as exc:  # noqa: BLE001
            logger.warning("dabai-lab 写后复盘失败 chapter=%s：%s", chapter_id, exc)
            db.rollback()
            events.put_nowait({"event": "debrief_done", "ok": False, "error": str(exc)})
    finally:
        db.close()
        events.put_nowait(None)


def spawn_post_write_pipeline(
    project_id: UUID,
    chapter_id: UUID,
    *,
    model_profile: str,
    llm_provider_id: Optional[UUID],
    user_id,
) -> asyncio.Queue:
    """启动写后流水线后台任务，返回事件队列（None 哨兵收尾）。

    调用方（SSE 生成器）负责 drain 队列并转发；被取消不影响任务完成。
    """
    events: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(_run_post_write_pipeline(
        project_id, chapter_id,
        model_profile=model_profile,
        llm_provider_id=llm_provider_id, user_id=user_id,
        events=events,
    ))
    _POST_WRITE_TASKS.add(task)
    task.add_done_callback(_POST_WRITE_TASKS.discard)
    return events
