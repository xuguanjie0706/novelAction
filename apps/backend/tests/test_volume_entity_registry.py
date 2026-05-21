"""volume_entity_registry 单元测试（无 LLM）。"""

from types import SimpleNamespace

from app.services.bootstrap.volume_entity_registry import (
    build_volume_entity_prompt_block,
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


def test_lint_orphan_faction_and_surname(monkeypatch):
    """模拟 DB：卷文本含未登记势力 + 主角姓与家族不符。"""
    vol = SimpleNamespace(
        title="第四卷",
        summary="幽姬（大魂师）率冥府进攻云霄剑宗",
        conflict="",
        hook="",
        sort_order=3,
        phase="climax",
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
    types = {i["type"] for i in issues}
    assert "faction_mismatch" in types
    descs = " ".join(i["description"] for i in issues)
    assert "云霄剑宗" in descs or "冥府" in descs
