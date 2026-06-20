"""LLM 错误文案与可重试判定回归。"""

from __future__ import annotations

import pytest

from app.services.ai_service import AIService
from app.services.ai.llm_response_text import extract_upstream_error
from app.services.llm_errors import (
    format_llm_error_message,
    is_llm_provider_failover_error,
    is_retryable_llm_error,
)


def test_format_connection_error():
    msg = format_llm_error_message(Exception("Connection error."))
    assert "无法连接大模型网关" in msg
    assert "测试连接" in msg


def test_retryable_connection_error():
    ai = AIService(profile="gemini")
    assert ai._is_retryable_llm_error(Exception("Connection error.")) is True
    assert is_retryable_llm_error(Exception("Connection error.")) is True
    assert is_retryable_llm_error(Exception("Server disconnected without sending a response.")) is True
    assert is_retryable_llm_error(Exception("Error code: 502")) is True


def test_format_server_disconnected_error():
    msg = format_llm_error_message(Exception("Server disconnected without sending a response."))
    assert "网关中途断开" in msg


def test_format_blocked_error():
    msg = format_llm_error_message(Exception("Your request was blocked."))
    assert "安全策略拦截" in msg
    assert "blocked" in msg.lower()


def test_format_peer_closed_stream_error():
    raw = "peer closed connection without sending complete message body (incomplete chunked read)"
    msg = format_llm_error_message(Exception(raw))
    assert "流式输出" in msg
    assert "参考章节" in msg
    assert raw in msg


def test_upstream_error_in_response_body():
    class FakeResp:
        error = {"message": "upstream error: do request failed", "code": "do_request_failed"}

    assert "upstream error" in extract_upstream_error(FakeResp())
    msg = format_llm_error_message(RuntimeError("大模型网关上游错误：upstream error: do request failed"))
    assert "换一条线路" in msg


def test_provider_failover_error_detection():
    assert is_llm_provider_failover_error(RuntimeError("LLM 返回空 choices，无法读取正文")) is True
    assert is_retryable_llm_error(RuntimeError("upstream error: do request failed")) is True
    assert is_llm_provider_failover_error(ValueError("json parse error")) is False


@pytest.mark.asyncio
async def test_chapter_coherence_check_returns_error_on_upstream_failure():
    async def boom(*_a, **_k):
        raise Exception("Your request was blocked.")

    svc = AIService(profile="gemini")
    svc._call_ai = boom
    result = await svc.chapter_coherence_check(
        project_title="测试",
        chapters=[
            {"id": "c1", "sort_order": 0, "title": "第1章", "content": "正文A"},
            {"id": "c2", "sort_order": 1, "title": "第2章", "content": "正文B"},
        ],
    )
    assert result.get("error")
    assert "安全策略拦截" in result["error"]
    assert result["overall_score"] == 0
