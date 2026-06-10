"""dabai 正文一致性校验 — 防误报回归。"""
from types import SimpleNamespace

from app.services.dabai.consistency_check import (
    _payoff_keywords,
    check_dabai_consistency,
)


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def query(self, model):
        return _FakeQuery([])


def test_dbc03_does_not_require_shuang_type_literal():
    anchors = _payoff_keywords(
        "全场寂静，叶辰步履稳健走入大门，众弟子吓得倒退三步",
        "守门弟子百般刁难",
    )
    plain = "..." + anchors[0] + "..."
    assert any(a in plain for a in anchors)


def test_check_passes_without_spurious_location_warnings():
    project = SimpleNamespace(id="p1", title="万古第一神体", extra={})
    plan = SimpleNamespace(
        id="plan1",
        parent_id=None,
        extra={
            "realm_rank": 2,
            "location_name": "青云外门",
            "dabai": {
                "shuang_type": "群嘲反转",
                "yaqu_setup": "守门弟子百般刁难",
                "shuang_payoff": "全场寂静，叶辰步履稳健走入大门，众弟子吓得倒退三步",
            },
        },
    )
    body = (
        "叶辰回到青云宗外门。守门弟子拦路嘲讽。"
        "叶辰随手一挥，全场寂静，众弟子吓得倒退三步。"
    )
    chapter = SimpleNamespace(
        content=f"<p>{body}</p>",
        sort_order=2,
        outline_node_id="plan1",
    )
    report = check_dabai_consistency(_FakeDB(), project, chapter, plan_node=plan)
    assert report["consistency_pass"] is True
    dbc03 = [w for w in report["warnings"] if w.get("rule_id") == "DBC-03"]
    assert not dbc03, dbc03
