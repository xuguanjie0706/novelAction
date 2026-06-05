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


class _FakeChapter:
    def __init__(self, chapter_id: str = "c1"):
        self.id = chapter_id
        self.project_id = "p1"
        self.title = "第2章 测试"
        self.sort_order = 1
        self.outline_node_id = None
        self.deleted_at = None
        self.content = ""


class _FakeQuery:
    def __init__(self, target):
        self._target = target

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._target


class _FakeDb:
    def __init__(self, record: _FakeRecord | None, chapter: _FakeChapter | None = None):
        self._record = record
        self._chapter = chapter or _FakeChapter()

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "Chapter":
            return _FakeQuery(self._chapter)
        if name == "PreWriteWarningRecord":
            return _FakeQuery(self._record)
        return _FakeQuery(None)


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
    db = _FakeDb(_FakeRecord("rec-1", warn_result))
    out = try_reuse_pre_write_brief_from_record(db, project_id="p1", chapter_id="c1")
    assert out is not None
    brief, evt = out
    assert len(brief.strip()) >= _MIN_REUSED_BRIEF_CHARS
    assert evt["event"] == "pre_warn_done"
    assert evt["reused"] is True
    assert evt["record_id"] == "rec-1"
    assert evt["risk_count"] >= 1


def test_try_reuse_returns_none_when_brief_too_thin():
    db = _FakeDb(_FakeRecord("rec-2", {"ok": True, "risk_count": 0}))
    assert try_reuse_pre_write_brief_from_record(db, project_id="p1", chapter_id="c1") is None
