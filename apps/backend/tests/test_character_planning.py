"""character_planning 单元测试。"""

from types import SimpleNamespace

from app.services.bootstrap.character_planning import (
    normalize_roster_boss_planning,
    planning_peak_realm,
    realms_equivalent,
)
from app.services.bootstrap.antagonist_roster import lint_antagonist_roster_issues


def test_realms_equivalent_sub_stage():
    names = ["斗之气", "斗气者", "斗师", "大斗师", "斗王"]
    assert realms_equivalent("大斗师初期", "大斗师", level_names=names)
    assert not realms_equivalent("斗气者", "大斗师", level_names=names)


def test_normalize_keeps_debut_not_climax_in_current():
    char = SimpleNamespace(
        name="叶海天",
        role="antagonist",
        character_tier="arc",
        current_realm="大斗师初期",
        extra={},
    )
    entry = {
        "vol_index": 0,
        "realm_at_debut": "斗气者九段",
        "realm_at_climax": "大斗师初期",
        "realm_at_climax_rank": 3,
    }
    changed = normalize_roster_boss_planning(
        char, entry, level_names=["斗之气", "斗气者", "斗师", "大斗师", "斗王"],
    )
    assert changed
    assert char.current_realm == "斗气者九段"
    assert planning_peak_realm(char) == "大斗师初期"


def test_lint_no_false_positive_debut_vs_climax():
    """current=登场境、peak=对决境时，不得与卷纲 BOSS 境界误报冲突。"""
    vol = SimpleNamespace(
        title="第一卷",
        sort_order=0,
        extra={"volume_boss": "叶海天", "volume_boss_realm": "大斗师初期"},
    )
    char = SimpleNamespace(
        name="叶海天",
        role="antagonist",
        character_tier="arc",
        current_realm="斗气者",
        extra={"peak_realm": "大斗师初期"},
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
                return FakeQuery([char])
            return FakeQuery([])

    ctx = {
        "antagonist_ladder": [{
            "vol_index": 0,
            "boss_name": "叶海天",
            "realm_at_debut": "斗气者",
            "realm_at_climax": "大斗师初期",
            "realm_at_climax_rank": 3,
        }],
        "power_level_names": ["斗之气", "斗气者", "斗师", "大斗师", "斗王"],
        "power_level_registry": {},
    }
    issues = lint_antagonist_roster_issues(FakeDB(), "pid", ctx)
    assert not any(i["type"] == "realm_mismatch" for i in issues)
