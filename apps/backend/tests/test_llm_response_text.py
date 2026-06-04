"""llm_response_text 单元测试。"""
from app.services.ai.llm_response_text import extract_llm_response_text, message_completion_text


class _FakeMsg:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_extract_llm_response_text_strips_think_outside_json():
    raw = '<think>内部推理</think>\n{"ok": true}'
    assert extract_llm_response_text(raw) == '{"ok": true}'


def test_extract_llm_response_text_salvages_json_inside_think():
    raw = '<think>\n{"summary": "复盘"}\n</think>'
    assert extract_llm_response_text(raw) == '{"summary": "复盘"}'


def test_message_completion_text_prefers_content():
    msg = _FakeMsg(content='{"a": 1}', reasoning_content="推理")
    assert message_completion_text(msg).startswith('{"a"')


def test_message_completion_text_empty_returns_empty():
    assert message_completion_text(_FakeMsg(content="")) == ""
