"""
draft_graph/events.py — SSE 事件 pub/sub 与 DB 持久化辅助。

职责（单一）：
  1. 维护 job_id → Queue 订阅表（供 WS/SSE 端点消费）
  2. 提供 emit() 函数：同步推实时队列 + 持久化到 GenerationJob.events
  3. 提供 update_job() 函数：更新 job 的 status / current_node / progress_pct 等元信息

此模块不含业务逻辑，不直接调用 AI 服务。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from app.database import SessionLocal
from app.models.generation_job import GenerationJob

logger = logging.getLogger(__name__)

# ── 实时订阅注册表 ──────────────────────────────────────────────────────
# job_id → list[asyncio.Queue]
_registry: dict[str, list[asyncio.Queue]] = {}

# 内部哨兵：SSE/WS 端点收到此项后关闭连接
_SENTINEL = {"event": "__stream_end__"}


def subscribe(job_id: str) -> asyncio.Queue:
    """注册 SSE/WS 订阅 Queue，容量 1024；重连时调用此函数重新订阅。"""
    q: asyncio.Queue = asyncio.Queue(maxsize=1024)
    _registry.setdefault(job_id, []).append(q)
    return q


def unsubscribe(job_id: str, q: asyncio.Queue) -> None:
    """连接断开后注销 Queue，防止内存泄漏。"""
    subs = _registry.get(job_id, [])
    if q in subs:
        subs.remove(q)


def _push(job_id: str, payload: dict) -> None:
    """同步 push 到所有订阅 Queue（满则丢弃 token 级事件，避免阻塞图执行）。"""
    for q in list(_registry.get(job_id, [])):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # token 级事件允许丢弃；node_start/done 等关键事件在调用处已做持久化兜底
            if payload.get("event") not in ("token",):
                logger.warning(
                    "SSE queue full for job %s, dropping event=%s",
                    job_id,
                    payload.get("event"),
                )


def emit(
    job_id: str,
    event: str,
    *,
    persist: bool = True,
    **kwargs: Any,
) -> None:
    """
    推送一条 SSE 事件到实时队列，并可选持久化到 GenerationJob.events。

    @param job_id: 目标 job UUID 字符串
    @param event: 事件名，如 node_start / token / waiting_input / job_complete
    @param persist: 是否写入 DB（token 级事件设为 False 以减少 DB 写压力）
    @param kwargs: 附加到事件 payload 的业务字段
    """
    payload: dict[str, Any] = {"event": event, **kwargs, "ts": int(time.time() * 1000)}
    _push(job_id, payload)
    if persist:
        _persist_event(job_id, payload)


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    current_node: str | None = None,
    progress_pct: int | None = None,
    user_input_schema: dict | None = None,
    result: dict | None = None,
    error_detail: str | None = None,
) -> None:
    """
    更新 GenerationJob 的元信息字段（非 events 追加，而是字段覆写）。

    供各节点在 node_start / waiting_input / node_done 时调用，更新前端可见状态。

    @param job_id: 目标 job UUID 字符串
    @param status: 新状态（None=不修改）
    @param current_node: 当前节点名（None=不修改）
    @param progress_pct: 0-100 进度（None=不修改）
    @param user_input_schema: waiting_input 时的输入描述（None=不修改）
    @param result: completed 时的结果（None=不修改）
    @param error_detail: failed 时的错误详情（None=不修改）
    """
    db = SessionLocal()
    try:
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if not job:
            logger.warning("update_job: job %s not found", job_id)
            return
        if status is not None:
            job.status = status
        if current_node is not None:
            job.current_node = current_node
        if progress_pct is not None:
            job.progress_pct = progress_pct
        if user_input_schema is not None:
            job.user_input_schema = user_input_schema
        if result is not None:
            job.result = result
        if error_detail is not None:
            job.error_detail = error_detail
        if status in ("completed", "failed", "cancelled"):
            job.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        logger.exception("update_job failed for job %s", job_id)
        db.rollback()
    finally:
        db.close()


def send_sentinel(job_id: str) -> None:
    """向所有订阅者推送流结束哨兵，触发 WS/SSE 连接关闭。"""
    _push(job_id, _SENTINEL)


# ── 内部辅助 ────────────────────────────────────────────────────────────

def _persist_event(job_id: str, payload: dict) -> None:
    """追加一条事件到 GenerationJob.events（JSON 数组）。"""
    db = SessionLocal()
    try:
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if not job:
            return
        job.events = list(job.events or []) + [payload]
        db.commit()
    except Exception:
        logger.exception("_persist_event failed for job %s", job_id)
        db.rollback()
    finally:
        db.close()
