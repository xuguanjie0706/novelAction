"""LLM 积分计费用户上下文（ContextVar）。

设计动机：
- 若在每个路由手动 ``AIService(..., user_id=...)``，极易漏接（如大纲 AI 曾长期未传 user）。
- FastAPI 没有「包一层就自动注入」的官方路由装饰器；用 **请求级 ContextVar**
  可在 ``SamplingMixin._call_ai`` / ``_stream_ai`` 统一解析扣费主体，与路由解耦。
- ``AIService`` 构造时显式传入的 ``user_id`` 优先于上下文（便于后台任务、脚本覆写）。

HTTP 入口在 ``main.py`` 注册 ``@app.middleware("http")``，按 Bearer JWT 调用
:func:`push_llm_billing_user` / :func:`pop_llm_billing_user`。

非 HTTP 场景（WebSocket ``?token=``、离线脚本、单元测试）请使用
:func:`bind_llm_billing_user` 在调用链外层绑定 UUID。
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Optional
from uuid import UUID

from app.config import settings
from app.utils.auth import decode_access_token_full

_llm_billing_user_id: ContextVar[Optional[UUID]] = ContextVar("llm_billing_user_id", default=None)


def push_llm_billing_user(user_id: Optional[UUID]) -> Token[Optional[UUID]]:
    """压入计费用户并返回用于 :func:`pop_llm_billing_user` 的 reset token。"""
    return _llm_billing_user_id.set(user_id)


def pop_llm_billing_user(token: Token[Optional[UUID]]) -> None:
    """与 ``push_llm_billing_user`` 配对，在 ``finally`` 中恢复外层上下文。"""
    _llm_billing_user_id.reset(token)


def get_llm_billing_user_id() -> Optional[UUID]:
    """返回当前异步上下文中绑定的计费用户 id；未绑定时为 None。"""
    return _llm_billing_user_id.get()


def resolve_llm_billing_user_id(explicit: Optional[UUID]) -> Optional[UUID]:
    """解析用于 ``log_llm_call`` / 积分预检的用户 id。

    Args:
        explicit: ``AIService`` 构造参数 ``user_id``；非空时直接采用。

    Returns:
        显式值；否则回退到 ContextVar 中的请求级绑定。
    """
    if explicit is not None:
        return explicit
    return get_llm_billing_user_id()


def billing_user_id_from_authorization_header(authorization: Optional[str]) -> Optional[UUID]:
    """从 ``Authorization: Bearer <jwt>`` 解析应对 LLM 计费的用户 UUID。

    与 ``dependencies.get_current_user`` 对齐：管理员 token、无效 admin、验签失败均返回 None
    （不扣费；具体路由仍会做 401/404）。

    Args:
        authorization: 原始 Authorization 头；缺失或非 Bearer 时返回 None。
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    raw = authorization[7:].strip()
    payload = decode_access_token_full(raw)
    if not payload:
        return None
    role = payload.get("role")
    sub = payload.get("sub")
    if role == "admin":
        if not settings.ADMIN_USERNAME or sub != settings.ADMIN_USERNAME:
            return None
        return None
    if not sub:
        return None
    try:
        return UUID(str(sub))
    except ValueError:
        return None


@contextmanager
def bind_llm_billing_user(user_id: Optional[UUID]) -> Iterator[None]:
    """在同步或 async 代码块内临时绑定计费用户（供 WS、脚本、测试使用）。

    Args:
        user_id: 应对账扣费的用户 UUID；None 表示本段不扣费。
    """
    tok = push_llm_billing_user(user_id)
    try:
        yield
    finally:
        pop_llm_billing_user(tok)
