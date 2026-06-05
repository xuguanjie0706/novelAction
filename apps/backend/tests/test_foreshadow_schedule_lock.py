"""伏笔日程锁定表与台账格式、sync 去重回归。"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.services.ai.foreshadow_schedule_lock import (
    _build_audit_phrases,
    _detect_outline_early_lay,
    _detect_outline_early_lay_from_ops,
    audit_early_foreshadow_plants,
    build_foreshadow_ledger,
    format_foreshadow_ledger_line,
    merge_early_plant_audit_into_qc_result,
    merge_foreshadow_schedule_into_warn_result,
)
from app.services.bootstrap.foreshadow_sync import _find_existing_for_lay, _keywords_overlap


def test_ledger_line_shows_planned_lay_and_resolve():
    fs = SimpleNamespace(
        code="F-001",
        title="十三指青印",
        description="测试",
        laid_chapter_number=5,
        planned_resolve_chapter=305,
        extra={"is_core_mystery": True, "mystery_name": "脊骨上的十三指青印"},
    )
    mysteries = [{"name": "脊骨上的十三指青印", "lay_chapter": 5}]
    line = format_foreshadow_ledger_line(fs, 1, {"脊骨上的十三指青印": mysteries[0]})
    assert "计划埋第5章" in line
    assert "预计回收第305章" in line
    assert "【⏳未到埋设章】" in line


def test_detect_outline_early_lay_conflict():
    forbidden = [{
        "name": "十三指青印",
        "planned_lay_chapter": 5,
        "keywords": ["十三指青印", "青印"],
        "reason": "计划第5章才埋",
    }]
    raw = "埋[十三指青印|主题:上界算计]"
    conflicts = _detect_outline_early_lay(raw, forbidden)
    assert len(conflicts) == 1
    assert "十三指" in conflicts[0]["outline_text"]


def test_detect_outline_early_lay_from_ops_conflict():
    forbidden = [{
        "name": "十三指青印",
        "planned_lay_chapter": 5,
        "keywords": ["十三指青印", "青印"],
        "reason": "计划第5章才埋",
    }]
    ops = [{"op": "lay", "name": "十三指青印", "theme": "上界算计"}]
    conflicts = _detect_outline_early_lay_from_ops(ops, forbidden)
    assert len(conflicts) == 1
    assert conflicts[0]["field"] == "foreshadow_ops"


def test_merge_schedule_adds_critical_risk():
    lock = {
        "has_schedule": True,
        "current_chapter_number": 1,
        "forbidden_early_plants": [{
            "name": "黑珠",
            "planned_lay_chapter": 3,
            "reason": "第3章才埋",
        }],
        "allowed_this_chapter": [],
        "opening_teases": [{"label": "第1章末钩子", "detail": "滴答声"}],
        "outline_conflicts": [{
            "field": "foreshadow",
            "outline_text": "黑珠跳动",
            "reason": "章纲提前埋设黑珠",
        }],
    }
    warn = {"ok": True, "risk_count": 0, "risks": [], "reminders": []}
    out = merge_foreshadow_schedule_into_warn_result(warn, lock)
    assert out["ok"] is False
    assert out["foreshadow_schedule_lock"]["has_schedule"] is True
    assert any(r.get("severity") == "critical" for r in out["risks"])


def test_keywords_overlap():
    assert _keywords_overlap("黑珠跳动", "腹中黑珠")
    assert _keywords_overlap("十三指青印", "十三指青印")


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, foreshadows, mysteries=None):
        self._foreshadows = foreshadows
        self._mysteries = mysteries or []

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "Foreshadow":
            return _FakeQuery(self._foreshadows)
        if name == "Project":
            proj = SimpleNamespace(
                extra={"core_mysteries": self._mysteries},
            )
            return _FakeQuery([proj])
        return _FakeQuery([])


def test_find_existing_for_lay_matches_core_mystery():
    pid = uuid.uuid4()
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        title="黑珠倒计时",
        description="【核心谜题】腹中黑珠",
        status="open",
        laid_chapter_number=3,
        laid_chapter_id=None,
        extra={
            "is_core_mystery": True,
            "mystery_name": "腹中「滴答」的黑珠",
            "planned_lay_chapter": 3,
        },
    )
    db = _FakeDb([existing], mysteries=[{"name": "腹中「滴答」的黑珠", "lay_chapter": 3}])
    found = _find_existing_for_lay(db, pid, "黑珠跳动")
    assert found is existing


def test_audit_early_plant_detects_forbidden_keyword():
    lock = {
        "forbidden_early_plants": [{
            "name": "腹中黑珠",
            "planned_lay_chapter": 5,
            "keywords": ["黑珠", "腹中"],
            "audit_phrases": ["腹中黑珠"],
        }],
    }
    hits = audit_early_foreshadow_plants("他感到腹中黑珠轻轻跳动。", lock)
    assert len(hits) == 1
    assert hits[0]["matched_keyword"] == "腹中黑珠"


def test_build_audit_phrases_filters_short_keywords():
    phrases = _build_audit_phrases("腹中黑珠", ["黑珠", "腹中黑珠"], "黑珠跳动声")
    assert "腹中黑珠" in phrases
    assert "黑珠" not in phrases
    assert phrases[0] == "腹中黑珠"  # 谜题名优先于 lay_method 子串


def test_audit_early_plant_ignores_short_keyword_fragment():
    """2～3 字关键词不应单独触发违约（降低误杀）。"""
    lock = {
        "forbidden_early_plants": [{
            "name": "太虚古殿",
            "planned_lay_chapter": 10,
            "keywords": ["古殿"],
            "audit_phrases": ["太虚古殿"],
        }],
    }
    hits = audit_early_foreshadow_plants("他独自走进一座破败古殿。", lock)
    assert hits == []


def test_merge_early_plant_audit_caps_score():
    qc = {"overall_score": 8.2, "dimensions": {"plot": {"score": 8.0, "comment": ""}}, "issues": [], "suggestions": []}
    violations = [{
        "name": "黑珠",
        "planned_lay_chapter": 5,
        "matched_keyword": "黑珠",
        "description": "违约",
    }]
    out = merge_early_plant_audit_into_qc_result(qc, violations)
    assert out["overall_score"] <= 5.5
    assert out["foreshadow_early_plant_violations"]


def test_build_foreshadow_ledger_batch():
    fs = SimpleNamespace(
        code="F-002",
        title="黑珠",
        description="desc",
        laid_chapter_number=None,
        planned_resolve_chapter=275,
        extra={"planned_lay_chapter": 3, "mystery_name": "腹中黑珠"},
    )
    text = build_foreshadow_ledger([fs], 1, [{"name": "腹中黑珠", "lay_chapter": 3}])
    assert "F-002" in text
    assert "计划埋第3章" in text
