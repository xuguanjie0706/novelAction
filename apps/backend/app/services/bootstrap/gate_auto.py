"""Bootstrap 自动模式：闸门 / 步骤重试处无需人工确认，由后端链式 resume。

``gate_data.auto_mode=true`` 时在 ``awaiting_gate`` / ``awaiting_retry`` 后自动
提交 approve 或 retry_step，直至终态或无法构造 resume 载荷。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

from app.database import SessionLocal
from app.models.bootstrap_run import BootstrapRun
from app.schemas.bootstrap_fanqie_positioning import try_validate_fanqie_positioning
from app.schemas.bootstrap_positioning import try_validate_positioning

logger = logging.getLogger(__name__)

_AUTO_RESUME_TASKS: dict[str, asyncio.Task] = {}
_MAX_AUTO_RESUME_ROUNDS = 16


def is_auto_mode(gate_data: Any) -> bool:
    """是否启用自动模式（存于 BootstrapRun.gate_data）。"""
    return bool(isinstance(gate_data, dict) and gate_data.get("auto_mode"))


def merge_gate_data_with_auto_mode(gate_data: dict | None, auto_mode: bool) -> dict:
    """创建 run 时写入 gate_data 根字段。"""
    base = dict(gate_data) if isinstance(gate_data, dict) else {}
    if auto_mode:
        base["auto_mode"] = True
    else:
        base.pop("auto_mode", None)
    return base


def build_auto_resume_payload(run: BootstrapRun) -> dict | None:
    """根据 run 状态构造 LangGraph Command(resume=...) 载荷；无法自动时返回 None。"""
    gd = run.gate_data if isinstance(run.gate_data, dict) else {}

    if run.status == "awaiting_retry" or gd.get("kind") == "step_retry":
        step = str(gd.get("step") or "").strip()
        return {"action": "retry_step", "step": step} if step else None

    if run.status != "awaiting_gate":
        return None

    kind = gd.get("kind") or "positioning"
    if kind == "positioning":
        raw = gd.get("positioning")
        if not isinstance(raw, dict) or not raw:
            logger.warning("auto_mode: run %s 缺少 positioning，无法自动 resume", run.id)
            return None
        if run.mode == "fanqie":
            normalized, err = try_validate_fanqie_positioning(raw)
        else:
            normalized, err = try_validate_positioning(raw)
        if err or normalized is None:
            logger.warning("auto_mode: positioning 校验失败 run=%s: %s", run.id, err)
            return None
        return {"action": "approve", "positioning": normalized}

    return {"action": "approve"}


def schedule_auto_resume_if_needed(
    run_id: str,
    *,
    mode: str,
    model_profile: str,
    llm_provider_id: Any,
    user_id: Any,
    resume_fn: Callable[..., Awaitable[None]],
) -> None:
    """若 run 为自动模式且停在闸门/重试，排队后台链式 resume（防重复任务）。"""
    db = SessionLocal()
    try:
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if not run or not is_auto_mode(run.gate_data):
            return
        if run.status not in ("awaiting_gate", "awaiting_retry"):
            return
        if build_auto_resume_payload(run) is None:
            return
    finally:
        db.close()

    existing = _AUTO_RESUME_TASKS.get(run_id)
    if existing and not existing.done():
        return

    task = asyncio.create_task(
        _auto_resume_chain(
            run_id,
            mode=mode,
            model_profile=model_profile,
            llm_provider_id=llm_provider_id,
            user_id=user_id,
            resume_fn=resume_fn,
        ),
        name=f"bootstrap-auto-{run_id[:8]}",
    )
    _AUTO_RESUME_TASKS[run_id] = task

    def _cleanup(t: asyncio.Task) -> None:
        if _AUTO_RESUME_TASKS.get(run_id) is t:
            _AUTO_RESUME_TASKS.pop(run_id, None)

    task.add_done_callback(_cleanup)


async def _auto_resume_chain(
    run_id: str,
    *,
    mode: str,
    model_profile: str,
    llm_provider_id: Any,
    user_id: Any,
    resume_fn: Callable[..., Awaitable[None]],
) -> None:
    """循环 resume 直至非暂停态或达到轮次上限。"""
    await asyncio.sleep(0.12)

    for round_i in range(_MAX_AUTO_RESUME_ROUNDS):
        db = SessionLocal()
        try:
            run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
            if not run or not is_auto_mode(run.gate_data):
                return
            if run.status in ("done", "failed", "cancelled"):
                return
            payload = build_auto_resume_payload(run)
            if not payload:
                logger.info(
                    "auto_mode: run %s 停止自动 resume（status=%s round=%s）",
                    run_id,
                    run.status,
                    round_i,
                )
                return
            mp = model_profile or run.model_profile or "gemini"
        finally:
            db.close()

        logger.info(
            "auto_mode: run %s 自动 resume round=%s action=%s",
            run_id,
            round_i,
            payload.get("action"),
        )
        try:
            await resume_fn(
                run_id,
                payload,
                model_profile=mp,
                llm_provider_id=llm_provider_id,
                user_id=user_id,
            )
        except Exception:
            logger.exception("auto_mode: resume 失败 run=%s", run_id)
            return

        await asyncio.sleep(0.18)

    logger.warning("auto_mode: run %s 达到最大自动 resume 轮次 %s", run_id, _MAX_AUTO_RESUME_ROUNDS)
