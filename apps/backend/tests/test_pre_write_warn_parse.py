"""写前预警解析与可复用判定。"""

from app.services.ai.pre_write_warn_parse import (
    has_usable_pre_write_body,
    looks_truncated_json,
    parse_pre_write_warning_text,
)


def test_looks_truncated_json():
    assert looks_truncated_json('{"a": 1')
    assert not looks_truncated_json('{"a": 1}')


def test_has_usable_pre_write_body_rejects_parse_failed():
    assert not has_usable_pre_write_body({"error": "x", "parse_failed": True})


def test_parse_minimal_pre_write_warning():
    raw = """```json
{
  "ok": true,
  "risk_count": 0,
  "protagonist_fact_sheet": {"realm": "筑基", "location": "洞府", "key_skills": [], "key_items": [], "forbidden": []},
  "writing_brief": {"opening_strategy": "动作开场", "conflict_structure": "", "closing_hook": "", "word_rhythm": ""},
  "must_events": [],
  "hallucination_traps": [],
  "risks": [],
  "reminders": []
}
```"""
    out = parse_pre_write_warning_text(raw)
    assert out["protagonist_fact_sheet"]["realm"] == "筑基"
    assert has_usable_pre_write_body(out)
