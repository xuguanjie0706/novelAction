"""volume_entity_registry 单元测试（无 LLM）。"""

from types import SimpleNamespace

from app.services.bootstrap.volume_entity_registry import (
    build_volume_entity_prompt_block,
    format_volume_realm_fix_hint,
    lint_volume_entity_issues,
    _extract_orgs,
    _org_matches_canonical,
)


def test_build_prompt_includes_factions_and_levels():
    ctx = {
        "faction_names": ["凌云宗", "噬魂殿"],
        "power_level_names": ["魂徒", "魂师", "大魂师", "魂皇", "魂宗"],
        "char_realms": {"苏云": "魂徒", "幽姬": "大魂师"},
        "protagonist": "苏云",
        "protagonist_faction": "青州叶家",
    }
    block = build_volume_entity_prompt_block(ctx)
    assert "凌云宗" in block
    assert "禁止自创别名" in block
    assert "魂宗" in block
    assert "苏云" in block


def test_extract_orgs_and_canonical_match():
    text = "主角拜入云霄剑宗，与冥府对峙，凌云宗长老出面。"
    orgs = _extract_orgs(text, ["凌云宗", "噬魂殿"])
    assert "云霄剑宗" in orgs
    assert "冥府" in orgs
    assert "主角拜入云霄剑宗" not in orgs
    assert _org_matches_canonical("凌云宗", ["凌云宗", "噬魂殿"])
    assert not _org_matches_canonical("冥府", ["凌云宗", "噬魂殿"])


def test_lint_orphan_faction_not_direct_issue(monkeypatch):
    """卷文本含未登记势力名：不再直写 issue，改由 collect_faction_semantic_hints 供 AI 裁决。"""
    from app.services.bootstrap.volume_faction_hints import collect_faction_semantic_hints

    vol = SimpleNamespace(
        title="第四卷",
        summary="幽姬（大魂师）率冥府进攻云霄剑宗",
        conflict="",
        hook="",
        sort_order=3,
        phase="climax",
        extra={},
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

        def first(self):
            return self._items[0] if self._items else None

    class FakeDB:
        def query(self, model):
            name = getattr(model, "__name__", str(model))
            if name == "OutlineNode":
                return FakeQuery([vol])
            if name == "Faction":
                return FakeQuery([
                    SimpleNamespace(name="凌云宗"),
                    SimpleNamespace(name="噬魂殿"),
                ])
            if name == "Character":
                return FakeQuery([
                    SimpleNamespace(
                        name="苏云",
                        role="protagonist",
                        faction="青州叶家",
                        current_realm="魂徒",
                        realm_rank=0,
                    ),
                    SimpleNamespace(
                        name="幽姬",
                        role="antagonist",
                        faction="噬魂殿",
                        current_realm="大魂师",
                        realm_rank=2,
                    ),
                ])
            if name == "PowerSystem":
                return FakeQuery([])
            return FakeQuery([])

    ctx = {
        "faction_names": ["凌云宗", "噬魂殿"],
        "power_level_names": ["魂徒", "魂师", "大魂师", "魂皇", "魂宗"],
        "protagonist": "苏云",
        "protagonist_faction": "青州叶家",
        "char_realms": {"苏云": "魂徒", "幽姬": "大魂师"},
    }
    issues = lint_volume_entity_issues(FakeDB(), "pid", ctx)
    faction_issues = [i for i in issues if i.get("type") == "faction_mismatch"]
    assert faction_issues == []

    hints = collect_faction_semantic_hints(FakeDB(), "pid", ctx)
    joined = " ".join(hints)
    assert "云霄剑宗" in joined or "冥府" in joined


def test_lint_villain_realm_inversion_by_structured_fields(monkeypatch):
    """卷四 BOSS 境界低于卷三 → 必须检出 villain_alignment。"""
    vol3 = SimpleNamespace(
        title="第三卷",
        summary="沈苍海（命轮境）终战",
        conflict="",
        hook="",
        sort_order=2,
        phase="turning",
        extra={"volume_boss": "沈苍海", "volume_boss_realm": "命轮境"},
    )
    vol4 = SimpleNamespace(
        title="第四卷",
        summary="莫无极（灵台境）领袖对决",
        conflict="",
        hook="",
        sort_order=3,
        phase="climax",
        extra={"volume_boss": "莫无极", "volume_boss_realm": "灵台境"},
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

        def first(self):
            return self._items[0] if self._items else None

    class FakeDB:
        def query(self, model):
            name = getattr(model, "__name__", str(model))
            if name == "OutlineNode":
                return FakeQuery([vol3, vol4])
            if name == "Faction":
                return FakeQuery([])
            if name == "Character":
                return FakeQuery([
                    SimpleNamespace(
                        name="沈苍海",
                        role="antagonist",
                        faction="",
                        current_realm="命轮境",
                        realm_rank=4,
                        character_tier="arc",
                    ),
                    SimpleNamespace(
                        name="莫无极",
                        role="supporting",
                        faction="",
                        current_realm="灵台境",
                        realm_rank=2,
                        character_tier="arc",
                    ),
                ])
            if name == "PowerSystem":
                return FakeQuery([])
            return FakeQuery([])

    level_names = ["凝气境", "筑基境", "灵台境", "金丹境", "命轮境", "化神境"]
    ctx = {
        "faction_names": [],
        "power_level_names": level_names,
        "protagonist": "主角",
        "char_realms": {"沈苍海": "命轮境", "莫无极": "灵台境"},
    }
    issues = lint_volume_entity_issues(FakeDB(), "pid", ctx)
    alignment = [i for i in issues if i["type"] == "villain_alignment"]
    assert len(alignment) >= 1
    assert "莫无极" in alignment[0]["description"]
    assert "沈苍海" in alignment[0]["description"]

    hint = format_volume_realm_fix_hint(alignment)
    assert "致命战力曲线错误" in hint
    assert "莫无极" in hint


def test_lint_equal_major_rank_not_high_severity():
    """同大境、无小境标注 → 不应报 high villain_alignment。"""
    vol3 = SimpleNamespace(
        title="第三卷",
        summary="",
        conflict="",
        hook="",
        sort_order=2,
        phase="turning",
        extra={"volume_boss": "冥皇", "volume_boss_realm": "破虚境"},
    )
    vol4 = SimpleNamespace(
        title="第四卷",
        summary="",
        conflict="",
        hook="",
        sort_order=3,
        phase="climax",
        extra={"volume_boss": "司徒圣影", "volume_boss_realm": "破虚境"},
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

        def first(self):
            return self._items[0] if self._items else None

    class FakeDB:
        def query(self, model):
            name = getattr(model, "__name__", str(model))
            if name == "OutlineNode":
                return FakeQuery([vol3, vol4])
            if name == "Faction":
                return FakeQuery([])
            if name == "Character":
                return FakeQuery([])
            if name == "PowerSystem":
                return FakeQuery([])
            return FakeQuery([])

    level_names = ["凝气境", "筑基境", "灵台境", "金丹境", "命轮境", "破虚境", "归一境"]
    ctx = {
        "faction_names": [],
        "power_level_names": level_names,
        "protagonist": "主角",
    }
    issues = lint_volume_entity_issues(FakeDB(), "pid", ctx)
    high_align = [
        i for i in issues
        if i["type"] == "villain_alignment" and i.get("severity") == "high"
    ]
    assert len(high_align) == 0


def test_lint_protagonist_boss_gap():
    """Boss rank 超出主角卷末 +2 → protagonist_alignment。"""
    vol = SimpleNamespace(
        title="第五卷",
        summary="终战",
        conflict="",
        hook="",
        sort_order=4,
        phase="climax",
        extra={
            "protagonist_realm_start": "灵台境",
            "protagonist_realm_end": "灵台境",
            "protagonist_realm_end_rank": 2,
            "volume_boss_realm": "化神境",
            "volume_boss": "大魔",
        },
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

        def first(self):
            return self._items[0] if self._items else None

    class FakeDB:
        def query(self, model):
            name = getattr(model, "__name__", str(model))
            if name == "OutlineNode":
                return FakeQuery([vol])
            if name == "Faction":
                return FakeQuery([])
            if name == "Character":
                return FakeQuery([])
            if name == "PowerSystem":
                return FakeQuery([])
            return FakeQuery([])

    level_names = ["凝气境", "筑基境", "灵台境", "金丹境", "命轮境", "化神境"]
    ctx = {
        "faction_names": [],
        "power_level_names": level_names,
        "protagonist": "主角",
    }
    issues = lint_volume_entity_issues(FakeDB(), "pid", ctx)
    gap = [i for i in issues if i["type"] == "protagonist_alignment"]
    assert len(gap) >= 1
    assert "化神境" in gap[0]["description"]
