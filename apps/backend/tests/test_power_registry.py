"""power_registry 与修仙多轴不变量单元测试。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.bootstrap.power_registry import (
    build_draft_power_context_from_db,
    build_power_level_registry,
    format_power_context_block,
    merge_power_into_ctx,
    primary_level_names,
    resolve_realm_in_registry,
)
from app.services.bootstrap.steps.power_systems.architect import build_power_architecture, uses_multi_axis_power
from app.services.bootstrap.steps.power_systems.invariants import (
    apply_auto_fixes,
    normalize_primary_levels,
    rescale_chapter_budgets,
    validate_xianxia_bundle,
)


def _ps(name: str, axis: str, levels: list, *, ps_id=None):
    return SimpleNamespace(
        id=ps_id or uuid.uuid4(),
        name=name,
        system_type="cultivation",
        description="desc",
        cultivation_method=None,
        breakthrough_condition=None,
        special_rules=None,
        levels=levels,
        protagonist_current_rank=1,
        protagonist_end_rank=len(levels),
        extra={"axis_role": axis},
    )


def test_uses_multi_axis_for_xianxia():
    assert uses_multi_axis_power("仙侠") is True
    assert uses_multi_axis_power("xianxia") is True
    assert uses_multi_axis_power("悬疑") is False


def test_build_power_level_registry_unique_keys():
    primary = _ps(
        "修行",
        "primary",
        [{"rank": 1, "name": "炼气境"}, {"rank": 2, "name": "筑基境"}],
    )
    sect = _ps(
        "宗门",
        "sect",
        [{"rank": 1, "name": "外门弟子"}, {"rank": 2, "name": "内门弟子"}],
    )
    reg = build_power_level_registry([primary, sect])
    assert "炼气境" in reg
    assert "外门弟子" in reg
    assert reg["炼气境"]["axis"] == "primary"
    assert reg["外门弟子"]["axis"] == "sect"


def test_merge_power_into_ctx_full_fidelity():
    primary = _ps(
        "修行境界",
        "primary",
        [{"rank": i, "name": n} for i, n in enumerate(["炼气", "筑基", "金丹"], 1)],
    )
    path = _ps("剑意", "path", [{"rank": 1, "name": "剑意初成"}])
    ctx: dict = {}
    project = SimpleNamespace(extra={"cultivation_laws": {"breakthrough_law": "须渡劫"}})
    merge_power_into_ctx(ctx, [primary, path], project=project)

    assert len(ctx["power_systems_full"]) == 2
    assert ctx["power_level_names"] == ["炼气", "筑基", "金丹"]
    assert "炼气" in ctx["power_level_registry"]
    assert ctx["cultivation_laws"]["breakthrough_law"] == "须渡劫"
    assert "主轴" in ctx["power_summary"] or "修行" in ctx["power_summary"]


def test_format_power_context_block_lists_axes():
    ctx = {
        "power_systems_full": [
            {
                "axis_role": "primary",
                "name": "修行",
                "levels": [{"name": "炼气"}, {"name": "筑基"}],
                "visualization": "神识差距",
            }
        ],
        "power_level_names": ["炼气", "筑基"],
        "cultivation_laws": {"breakthrough_law": "金丹以上须渡劫"},
    }
    text = format_power_context_block(ctx)
    assert "修行主轴" in text
    assert "炼气" in text
    assert "渡劫" in text


def test_resolve_realm_fuzzy():
    reg = {"筑基境": {"raw_name": "筑基境", "rank": 2, "axis": "primary"}}
    assert resolve_realm_in_registry("筑基中期", reg) == "筑基境"
    assert resolve_realm_in_registry("未知境界", reg) is None


def test_rescale_chapter_budgets():
    levels = [{"chapter_budget": 10}, {"chapter_budget": 10}, {"chapter_budget": 10}]
    rescale_chapter_budgets(levels, 300)
    total = sum(lv["chapter_budget"] for lv in levels)
    assert 180 <= total <= 240


def test_validate_xianxia_bundle_missing_axes():
    arch = build_power_architecture({"genre": "仙侠", "target_words": 1_200_000})
    bundle = {"systems": [{"axis_role": "primary", "levels": []}], "cultivation_laws": {}}
    apply_auto_fixes(bundle, arch)
    errors = validate_xianxia_bundle(bundle, arch)
    assert any("至少" in e or "缺少" in e for e in errors)


def test_enrich_skill_from_grade():
    ctx = {
        "power_level_names": ["炼气", "筑基", "金丹"],
        "power_level_registry": {
            "炼气": {"axis": "primary", "rank": 1, "raw_name": "炼气"},
            "筑基": {"axis": "primary", "rank": 2, "raw_name": "筑基"},
            "金丹": {"axis": "primary", "rank": 3, "raw_name": "金丹"},
            "灵宝": {"axis": "artifact", "rank": 4, "raw_name": "灵宝"},
        },
        "power_systems_full": [
            {"axis_role": "artifact", "levels": [{"name": "凡品"}, {"name": "灵宝"}]},
        ],
    }
    from app.services.bootstrap.power_grade_align import enrich_item_power_fields, enrich_skill_power_fields

    sk = enrich_skill_power_fields({"grade": "sky", "name": " test"}, ctx)
    assert sk.get("level_required") in ctx["power_level_registry"]
    it = enrich_item_power_fields({"rarity": "legendary", "artifact_tier": "灵宝"}, ctx)
    assert it.get("artifact_tier") == "灵宝"


def test_path_alignment_detects_regression():
    """道途阶曲线：后期卷 ≤ 前期卷 → path_alignment。"""
    from app.services.bootstrap.volume_entity_registry import lint_volume_entity_issues

    vol1 = SimpleNamespace(
        title="第一卷", summary="", conflict="", hook="",
        sort_order=0, phase="opening",
        extra={"volume_boss_path_rank": "剑意三重"},
    )
    vol2 = SimpleNamespace(
        title="第二卷", summary="", conflict="", hook="",
        sort_order=1, phase="rising",
        extra={"volume_boss_path_rank": "剑意二重"},
    )

    class FakeQuery:
        def __init__(self, items):
            self._items = items

        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def all(self):
            return self._items

        def first(self):
            return self._items[0] if self._items else None

    class FakeDB:
        def query(self, model):
            name = getattr(model, "__name__", str(model))
            if name == "OutlineNode":
                return FakeQuery([vol1, vol2])
            return FakeQuery([])

    ctx = {
        "power_level_registry": {
            "剑意二重": {"axis": "path", "rank": 2, "raw_name": "剑意二重"},
            "剑意三重": {"axis": "path", "rank": 3, "raw_name": "剑意三重"},
        },
        "power_level_names": ["炼气", "筑基"],
    }
    issues = lint_volume_entity_issues(FakeDB(), "pid", ctx)
    assert any(i.get("type") == "path_alignment" for i in issues)


def test_build_draft_power_context_includes_axes():
    import uuid

    primary = SimpleNamespace(
        id=uuid.uuid4(),
        name="修行",
        system_type="cultivation",
        description="d",
        cultivation_method=None,
        breakthrough_condition="渡劫",
        special_rules=None,
        levels=[{"rank": 1, "name": "炼气"}, {"rank": 2, "name": "筑基"}],
        protagonist_current_rank=1,
        protagonist_end_rank=2,
        extra={"axis_role": "primary"},
    )
    path = SimpleNamespace(
        id=uuid.uuid4(),
        name="剑意",
        system_type="cultivation",
        description=None,
        cultivation_method=None,
        breakthrough_condition=None,
        special_rules=None,
        levels=[{"rank": 1, "name": "剑意初成"}],
        protagonist_current_rank=None,
        protagonist_end_rank=None,
        extra={"axis_role": "path", "path_id": "sword"},
    )
    project = SimpleNamespace(
        extra={"cultivation_laws": {"breakthrough_law": "金丹须渡劫"}, "dao_heart": {"heart_demon_triggers": ["执念"]}}
    )

    class _Q:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def first(self):
            return project

        def all(self):
            return [primary, path]

    class _DB:
        def query(self, model):
            return _Q([primary, path])

    text = build_draft_power_context_from_db(_DB(), "pid")
    assert "修行主轴" in text
    assert "道途" in text
    assert "渡劫" in text
    assert "执念" in text or "心魔" in text
