"""Bootstrap 步骤失败：暂停图执行并等待用户重试（LangGraph interrupt）。"""

from __future__ import annotations

from langgraph.types import interrupt

from app.services.bootstrap.graph import (
    BootstrapState,
    _persist,
    _resolve_config,
    _state_run_id,
    emit,
)


def user_wants_step_retry(user: dict | object | None) -> bool:
    """resume 载荷是否要求重跑当前失败步骤。"""
    return isinstance(user, dict) and user.get("action") == "retry_step"


async def pause_for_step_retry(
    state: BootstrapState,
    config: dict | None,
    *,
    step: str,
    message: str,
    ctx: dict,
    emit_error: bool = True,
) -> dict:
    """步骤失败后中断图；用户 ``retry_step`` resume 后由调用方 while 循环重试。

    Returns:
        LangGraph interrupt 恢复时的用户载荷（通常为 ``{"action": "retry_step"}``）。
    """
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)

    if emit_error:
        emit(run_id, "error", db, step=step, message=message)
    emit(
        run_id,
        "step_halted",
        db,
        persist_status="awaiting_retry",
        step=step,
        message=message,
    )
    _persist(
        db,
        run_id,
        {},
        gate_data={"kind": "step_retry", "step": step, "message": message},
    )
    user = interrupt({"kind": "step_retry", "step": step, "message": message})
    return user if isinstance(user, dict) else {}
