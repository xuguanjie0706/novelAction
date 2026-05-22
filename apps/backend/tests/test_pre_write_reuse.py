"""写前预警复用：整章重写时跳过重复 LLM 审稿。"""

from app.routers.ai.pre_write_for_draft import (
    _MIN_REUSED_BRIEF_CHARS,
    try_reuse_pre_write_brief_from_record,
)
from app.routers.ai.gated_draft_helpers import _build_pre_warn_prompt_block


class _FakeRecord:
    def __init__(self, rec_id: str, result: dict):
        self.id = rec_id
        self.result = result


class _FakeQuery:
    def __init__(self, record: _FakeRecord | None):
        self._record = record

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._record


class _FakeDb:
    def __init__(self, record: _FakeRecord | None):
        self._record = record

    def query(self, model):
        return _FakeQuery(self._record)


def test_try_reuse_returns_none_when_no_record():
    db = _FakeDb(None)
    assert try_reuse_pre_write_brief_from_record(
        db, project_id="p1", chapter_id="c1"
    ) is None


def test_try_reuse_returns_brief_when_record_has_writing_brief():
    warn_result = {
        "ok": True,
        "risk_count": 2,
        "protagonist_fact_sheet": {"realm": "筑基初期", "location": "青云宗"},
        "writing_brief": {
            "opening_strategy": "冲突开场",
            "conflict_structure": "外压+内疑",
            "closing_hook": "身份线索",
        },
        "must_events": ["主角识破陷阱"],
        "hallucination_traps": ["勿凭空升级境界"],
        "risks": [{"severity": "medium", "type": "continuity", "description": "上章伤势"}],
    }
    brief_expected = _build_pre_warn_prompt_block(warn_result).strip()
    assert len(brief_expected) >= _MIN_REUSED_BRIEF_CHARS

    db = _FakeDb(_FakeRecord("rec-1", warn_result))
    out = try_reuse_pre_write_brief_from_record(db, project_id="p1", chapter_id="c1")
    assert out is not None
    brief, evt = out
    assert brief == brief_expected
    assert evt["event"] == "pre_warn_done"
    assert evt["reused"] is True
    assert evt["record_id"] == "rec-1"
    assert evt["risk_count"] == 2


def test_try_reuse_returns_none_when_brief_too_thin():
    db = _FakeDb(_FakeRecord("rec-2", {"ok": True, "risk_count": 0}))
    assert try_reuse_pre_write_brief_from_record(db, project_id="p1", chapter_id="c1") is None
