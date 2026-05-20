"""LLM 错误文案与可重试判定回归。"""

from __future__ import annotations

from app.services.ai_service import AIService
from app.services.llm_errors import format_llm_error_message


def test_format_connection_error():
    msg = format_llm_error_message(Exception("Connection error."))
    assert "无法连接大模型网关" in msg
    assert "测试连接" in msg


def test_retryable_connection_error():
    ai = AIService(profile="gemini")
    assert ai._is_retryable_llm_error(Exception("Connection error.")) is True
