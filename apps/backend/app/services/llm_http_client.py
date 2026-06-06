"""OpenAI 兼容网关 HTTP 客户端工厂。

部分中转（如 one2api.xyz）会拦截 OpenAI SDK 默认 User-Agent（``OpenAI/Python``），
导致 AIService 路径返回 403 ``Your request was blocked``，而管理后台 httpx 测试仍显示联通。
业务侧统一使用中性 UA，避免「测试通过、生成失败」分叉。
"""
from __future__ import annotations

import httpx
import openai

from app.config import settings

LLM_HTTP_USER_AGENT = "novelaction/1.0"


def create_async_openai_client(*, base_url: str, api_key: str) -> openai.AsyncOpenAI:
    """构造带中性 User-Agent 的 ``AsyncOpenAI`` 客户端。"""
    ua_headers = {"User-Agent": LLM_HTTP_USER_AGENT}
    timeout = httpx.Timeout(
        connect=settings.LLM_HTTP_CONNECT_TIMEOUT,
        read=settings.LLM_HTTP_READ_TIMEOUT,
        write=120.0,
        pool=30.0,
    )
    http_client = httpx.AsyncClient(timeout=timeout, headers=ua_headers)
    return openai.AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        http_client=http_client,
        default_headers=ua_headers,
    )
