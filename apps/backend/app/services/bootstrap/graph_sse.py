"""
graph_sse.py — Bootstrap SSE 事件推送与持久化

职责：
- 管理 SSE 订阅队列注册表（subscribe / unsubscribe）
- 同步推送事件到所有订阅者
- 将事件持久化到 BootstrapRun.events 并可选更新 status 等字段
"""
from __future__ import annotations

import asyncio
import logging
import time

from app.models.bootstrap_run import BootstrapRun

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────
# SSE 事件扇出注册表
# ──────────────────────────────────────────────────────
_queue_registry: dict[str, list[asyncio.Queue]] = {}


def subscribe(run_id: str) -> asyncio.Queue:
    """注册 SSE 订阅 Queue，供 /events 端点消费。每个 item 是 event dict。"""
    q: asyncio.Queue = asyncio.Queue(maxsize=512)
    _queue_registry.setdefault(run_id, []).append(q)
    return q


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    """SSE 断开后注销 Queue，防止内存泄漏。"""
    subs = _queue_registry.get(run_id, [])
    if q in subs:
        subs.remove(q)


def push(run_id: str, payload: dict) -> None:
    """同步 push 到所有订阅队列（满则丢弃，不阻塞图执行）。"""
    for q in _queue_registry.get(run_id, []):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for run %s, dropping %s", run_id, payload.get("event"))


def persist(db, run_id: str, payload: dict, *, status: str | None = None, **extra) -> None:
    """追加 event 到 BootstrapRun.events；可同时更新 status 等字段。"""
    try:
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if not run:
            return
        if payload:
            run.events = list(run.events or []) + [payload]
        if status:
            run.status = status
        for k, v in extra.items():
            if k == "gate_data" and isinstance(v, dict):
                from app.services.bootstrap.gate_auto import merge_gate_data_snapshot
                v = merge_gate_data_snapshot(run.gate_data, v)
            setattr(run, k, v)
        db.commit()
        if run.status == "awaiting_gate" and "gate_data" in extra:
            gd = run.gate_data if isinstance(run.gate_data, dict) else {}
            if gd.get("auto_mode"):
                from app.services.bootstrap.gate_auto import schedule_auto_resume_for_run
                schedule_auto_resume_for_run(run_id)
    except Exception:
        logger.exception("Failed to persist event for run %s", run_id)
        db.rollback()


def emit(run_id: str, event: str, db=None, *, persist_status: str | None = None, **kwargs) -> None:
    """推送 SSE 事件：写实时队列 + 可选持久化到 BootstrapRun.events / 更新 status。"""
    payload = {"event": event, **kwargs, "ts": int(time.time() * 1000)}
    push(run_id, payload)
    if db is not None:
        persist(db, run_id, payload, status=persist_status)
