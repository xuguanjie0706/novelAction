"""llm_http_client — 中性 User-Agent 工厂测试。"""
from app.services.llm_http_client import LLM_HTTP_USER_AGENT, create_async_openai_client


def test_create_async_openai_client_uses_neutral_user_agent():
    client = create_async_openai_client(base_url="https://example.com/v1", api_key="test-key")
    assert client.default_headers.get("User-Agent") == LLM_HTTP_USER_AGENT
    assert "OpenAI/Python" not in (client.default_headers.get("User-Agent") or "")
