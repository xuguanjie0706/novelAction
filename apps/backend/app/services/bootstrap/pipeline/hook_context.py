"""运行期 Hook 上下文（contextvars，支持同 worker 并发 run）。"""
from __future__ import annotations

import contextvars

from app.services.bootstrap.pipeline.hooks import HookRegistry

_hooks_var: contextvars.ContextVar[HookRegistry | None] = contextvars.ContextVar(
    "bootstrap_pipeline_hooks", default=None,
)


def set_active_hooks(registry: HookRegistry | None) -> contextvars.Token:
    return _hooks_var.set(registry)


def reset_active_hooks(token: contextvars.Token) -> None:
    _hooks_var.reset(token)


def get_active_hooks() -> HookRegistry | None:
    return _hooks_var.get()


def collect_step_hooks(step: str, ctx: dict) -> str:
    reg = _hooks_var.get()
    if reg is None:
        return ""
    return reg.collect(step, ctx)
