"""LLM 调用日志：上下文截断 / 超限识别。"""

from app.services.llm_call_log import (
    is_context_limit_error,
    merge_truncation_into_context,
    resolve_context_issue,
)


def test_merge_truncation_into_context():
    ctx = merge_truncation_into_context({"operation": "draft"}, ["字段 foo 被截断"])
    assert ctx["context_truncated"] is True
    assert ctx["truncation_warnings"] == ["字段 foo 被截断"]
    assert ctx["operation"] == "draft"


def test_resolve_context_issue_truncated():
    assert (
        resolve_context_issue(
            {"context_truncated": True, "truncation_warnings": ["x"]},
            None,
            status="ok",
        )
        == "truncated"
    )


def test_resolve_context_issue_limit_exceeded():
    err = "Error: maximum context length is 8192 tokens"
    assert resolve_context_issue({}, err, status="error") == "limit_exceeded"


def test_is_context_limit_error_chinese():
    assert is_context_limit_error("请求失败：上下文长度超出模型限制")


def test_resolve_context_issue_none():
    assert resolve_context_issue({}, "connection timeout", status="error") is None


def test_row_to_dict_omits_payload_when_requested():
    from types import SimpleNamespace

    from app.services.llm_call_log import _row_to_dict

    row = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        created_at=None,
        mode="default",
        model="m",
        llm_endpoint="http://x/v1/chat/completions",
        status="ok",
        duration_ms=1,
        context={},
        token_usage={},
        error=None,
        input_payload={"messages": ["huge"]},
        output_payload={"text": "out"},
    )
    slim = _row_to_dict(row, include_payload=False)  # type: ignore[arg-type]
    assert "input_payload" not in slim
    assert "output_payload" not in slim
    full = _row_to_dict(row, include_payload=True)  # type: ignore[arg-type]
    assert full["input_payload"] == {"messages": ["huge"]}


def test_list_llm_calls_page_shape(monkeypatch):
    """分页返回结构含 items / total / page / page_size。"""
    from app.services import llm_call_log as mod

    class _FakeQ:
        def filter(self, *a, **k):
            return self

        def count(self):
            return 45

        def order_by(self, *a, **k):
            return self

        def options(self, *a, **k):
            return self

        def offset(self, n):
            return self

        def limit(self, n):
            return self

        def all(self):
            return []

    class _FakeDb:
        def query(self, *a, **k):
            return _FakeQ()

    monkeypatch.setattr(mod, "SessionLocal", lambda: _FakeDb())
    out = mod.list_llm_calls(page=2, page_size=20, db=_FakeDb())
    assert out["total"] == 45
    assert out["page"] == 2
    assert out["page_size"] == 20
    assert out["items"] == []
