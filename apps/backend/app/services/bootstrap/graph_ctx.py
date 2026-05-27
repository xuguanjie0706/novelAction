"""Bootstrap ctx 与 LangGraph state 边界：禁止不可序列化对象进入 checkpoint。"""

from __future__ import annotations


def sanitize_bootstrap_ctx(ctx: dict | None) -> dict:
    """移除 ctx 中不可 msgpack 序列化的条目（如 SQLAlchemy Session）。

    LangGraph checkpoint 会持久化 ``BootstrapState.ctx``；任何 ORM Session
  写入 ctx 都会在 resume / interrupt 时触发
  ``Type is not msgpack serializable: Session``。
    """
    if not ctx:
        return {}
    out = dict(ctx)
    out.pop("_db", None)
    for key in list(out.keys()):
        val = out[key]
        if type(val).__name__ == "Session" and callable(getattr(val, "query", None)):
            out.pop(key, None)
    return out
