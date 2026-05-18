"""
draft_graph/worker.py — 生成任务恢复引擎（服务器重启后的状态修复）。

职责：
  FastAPI startup 时调用 recover_stale_jobs()，扫描异常中断的任务并做恢复处理：
  - status=running：服务器崩溃时正在执行的任务，MemorySaver 已丢失 → 标为 failed
  - status=pending：已入队但未启动的任务 → 重新 enqueue（MemorySaver 无 checkpoint，
    从头重跑）

设计说明：
  MemorySaver 为进程内存，服务器重启后 checkpoint 丢失。
  当前选择「running → failed，pending → 重新启动」的保守策略：
  - running 任务已生成部分内容，重跑会覆盖，因此标 failed 让用户决定是否重提。
  - pending 任务尚未执行，重跑幂等，安全。

  若将来升级 PostgresSaver，running 任务也可尝试 resume（MemorySaver 换掉即可，
  worker 逻辑不变）。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models.generation_job import GenerationJob

logger = logging.getLogger(__name__)


async def recover_stale_jobs() -> None:
    """
    服务器启动时修复残留的异常任务状态。

    应在 FastAPI startup 事件中以 asyncio.create_task 调用，非阻塞。
    等待 2 秒让其他 startup 工作（DB 迁移等）完成后再执行。

    @raises 不抛出异常（内部全 try/except，启动失败不应阻断服务）
    """
    await asyncio.sleep(2)  # 等待 DB 连接池稳定
    db = SessionLocal()
    try:
        # ── 1. running → failed（MemorySaver 已丢失，无法 resume）────────
        stale_running = (
            db.query(GenerationJob)
            .filter(GenerationJob.status == "running")
            .all()
        )
        for job in stale_running:
            job.status = "failed"
            job.error_detail = "服务器重启，生成进度丢失。请重新提交任务。"
            job.completed_at = datetime.now(timezone.utc)
            _append_event(job, "job_failed", message="服务器重启，进度丢失")
        if stale_running:
            logger.warning(
                "recover_stale_jobs: marked %d running jobs as failed", len(stale_running)
            )

        # ── 2. waiting_input → failed（interrupt 已无法 resume）──────────
        stale_waiting = (
            db.query(GenerationJob)
            .filter(GenerationJob.status == "waiting_input")
            .all()
        )
        for job in stale_waiting:
            job.status = "failed"
            job.error_detail = "服务器重启，human interrupt 状态丢失。请重新提交任务。"
            job.completed_at = datetime.now(timezone.utc)
            _append_event(job, "job_failed", message="服务器重启，interrupt 状态丢失")
        if stale_waiting:
            logger.warning(
                "recover_stale_jobs: marked %d waiting_input jobs as failed",
                len(stale_waiting),
            )

        # ── 3. pending → 重新 enqueue（尚未执行，重跑幂等）───────────────
        pending_jobs = (
            db.query(GenerationJob)
            .filter(GenerationJob.status == "pending")
            .order_by(GenerationJob.created_at.asc())
            .all()
        )
        db.commit()

        if pending_jobs:
            logger.info(
                "recover_stale_jobs: re-enqueueing %d pending jobs", len(pending_jobs)
            )
            for job in pending_jobs:
                await _reenqueue(job)

    except Exception:
        logger.exception("recover_stale_jobs encountered an error")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


async def _reenqueue(job: GenerationJob) -> None:
    """
    将 pending 任务重新提交到后台队列。

    读取 input_payload 重建参数，调用 run_draft_job（仅 chapter_draft 类型）。
    其他 job_type 暂不支持，直接标 failed。

    @param job: GenerationJob ORM 对象（需先 commit 状态变更）
    """
    from app.services.draft_graph.graph import run_draft_job

    job_id = str(job.id)
    payload = job.input_payload or {}

    if job.job_type != "chapter_draft":
        logger.warning("_reenqueue: unsupported job_type=%s for job %s", job.job_type, job_id)
        return

    try:
        asyncio.create_task(
            run_draft_job(
                job_id=job_id,
                project_id=str(job.project_id),
                chapter_id=payload.get("chapter_id", ""),
                outline_node_id=payload.get("outline_node_id", ""),
                user_directives=payload.get("user_directives", ""),
                llm_provider_id=payload.get("llm_provider_id"),
                model_profile=payload.get("model_profile", "gemini"),
                quality_threshold=payload.get("quality_threshold", 75),
                skip_blueprint_review=payload.get("skip_blueprint_review", False),
                skip_quality_review=payload.get("skip_quality_review", False),
                max_iterations=payload.get("max_iterations", 3),
            ),
            name=f"draft-recover-{job_id[:8]}",
        )
        logger.info("_reenqueue: job %s re-enqueued", job_id)
    except Exception:
        logger.exception("_reenqueue failed for job %s", job_id)


def _append_event(job: GenerationJob, event: str, **kwargs) -> None:
    """向 job.events 追加一条事件（不 commit，由调用方统一 commit）。"""
    import time

    payload = {"event": event, **kwargs, "ts": int(time.time() * 1000)}
    job.events = list(job.events or []) + [payload]
