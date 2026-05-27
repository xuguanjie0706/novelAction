"""antagonist_roster / antagonist_ladder 单元测试。"""

from types import SimpleNamespace

from app.services.bootstrap.antagonist_roster import (
    bind_volume_boss_from_roster,
    format_ladder_summary,
    lint_antagonist_roster_issues,
    normalize_antagonist_ladder,
)


def _ctx():
    return {
        "protagonist": "林烬",
        "char_realms": {"林烬": "凝气境"},
        "power_level_names": ["凝气境", "筑基境", "灵台境", "金丹境", "命轮境", "化神境"],
        "power_level_registry": {},
        "power_systems_full": [{"axis_role": "primary", "protagonist_end_rank": 5}],
        "char_name_to_id": {"沈苍海": "uuid-1"},
        "antagonist_ladder": [
            {
                "vol_index": 0,
                "boss_name": "沈苍海",
                "realm_at_debut": "筑基境",
                "realm_at_climax": "灵台境",
                "realm_at_climax_rank": 2,
            },
        ],
    }


def test_normalize_ladder_fills_volume_count():
    ladder = normalize_antagonist_ladder([], _ctx(), 3)
    assert len(ladder) == 3
    assert ladder[0]["boss_name"]
    assert ladder[-1]["realm_at_climax_rank"] >= ladder[0]["realm_at_climax_rank"]


def test_bind_volume_boss_from_roster():
    ctx = _ctx()
    vol_extra: dict = {}
    bind_volume_boss_from_roster(
        0,
        {"volume_boss": "错误名", "volume_boss_realm": "凝气境"},
        vol_extra,
        ctx,
    )
    assert vol_extra["volume_boss"] == "沈苍海"
    assert vol_extra["volume_boss_realm"] == "灵台境"
    assert vol_extra["volume_boss_character_id"] == "uuid-1"


def test_lint_missing_boss_character():
    vol = SimpleNamespace(
        title="第一卷",
        sort_order=0,
        extra={"volume_boss": "沈苍海", "volume_boss_realm": "灵台境"},
    )

    class FakeQuery:
        def __init__(self, items):
            self._items = items

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return self._items

    class FakeDB:
        def query(self, model):
            name = getattr(model, "__name__", str(model))
            if name == "OutlineNode":
                return FakeQuery([vol])
            if name == "Character":
                return FakeQuery([])
            return FakeQuery([])

    issues = lint_antagonist_roster_issues(FakeDB(), "pid", _ctx())
    assert any("未在人物库建档" in i["description"] for i in issues)


def test_format_ladder_summary():
    s = format_ladder_summary(_ctx()["antagonist_ladder"])
    assert "沈苍海" in s
    assert "灵台境" in s
