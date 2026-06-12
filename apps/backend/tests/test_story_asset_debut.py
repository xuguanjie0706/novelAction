"""story_assets debut 裁决与台账种子修复。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.dabai_lab import DabaiAsset, DabaiClue, DabaiRelation
from app.services.dabai.lab_ledger_seed import (
    reconcile_misseeded_protagonist_skills,
    seed_ledgers,
)
from app.services.dabai.story_asset_debut import (
    plot_role_from_description,
    resolve_plot_asset_debut,
)


def test_growth_line_skill_forces_later():
    asset = {
        "kind": "skill",
        "plot_role": "成长线",
        "owner": "李夜",
        "debut": "start",
    }
    assert resolve_plot_asset_debut(asset, "李夜") == "later"


def test_protagonist_skill_forces_later():
    asset = {"kind": "skill", "plot_role": "底牌", "owner": "李夜", "debut": "start"}
    assert resolve_plot_asset_debut(asset, "李夜") == "later"


def test_others_item_can_start():
    asset = {"kind": "item", "plot_role": "争夺点", "owner": "赵猛", "debut": "start"}
    assert resolve_plot_asset_debut(asset, "李夜") == "start"


def test_protagonist_heirloom_item_can_start():
    asset = {"kind": "item", "plot_role": "身世信物", "owner": "李夜", "debut": "start"}
    assert resolve_plot_asset_debut(asset, "李夜") == "start"


def test_plot_role_from_description():
    assert plot_role_from_description("[成长线] 主功法") == "成长线"
    assert plot_role_from_description("无括号") == ""


def _orm_cls(model):
    """``db.query(DabaiAsset.id)`` 传入的是列描述符，需取 class_。"""
    return getattr(model, "class_", model)


def test_seed_ledgers_adds_golden_finger_when_story_assets_ran_first():
    """story_assets 先写入 seed 资产时，仍应补种金手指。"""
    project = SimpleNamespace(
        id="proj-1",
        golden_finger={"name": "寂灭万魂幡", "core_ability": "收魂代修"},
        characters=[SimpleNamespace(name="李夜", role="主角", function="")],
    )
    asset_calls = {"n": 0}

    def query_side_effect(model):
        chain = MagicMock()
        cls = _orm_cls(model)
        if cls is DabaiAsset:
            asset_calls["n"] += 1
            if asset_calls["n"] == 1:
                chain.filter.return_value.first.return_value = None
            else:
                chain.filter.return_value.all.return_value = []
        elif cls is DabaiRelation:
            chain.filter.return_value.first.return_value = object()
        return chain

    db = MagicMock()
    db.query.side_effect = query_side_effect

    seed_ledgers(db, project)  # type: ignore[arg-type]
    db.add.assert_called()
    added = db.add.call_args[0][0]
    assert added.kind == "golden_finger"
    assert added.name == "寂灭万魂幡"
    db.commit.assert_called_once()


def test_reconcile_moves_misseeded_growth_skill():
    asset = SimpleNamespace(
        name="九转噬魂经",
        description="[成长线] 转化幡力",
    )
    skill_query = MagicMock()
    skill_query.filter.return_value.all.return_value = [asset]
    clue_query = MagicMock()
    clue_query.filter.return_value.first.return_value = None

    def query_side_effect(model):
        cls = _orm_cls(model)
        if cls is DabaiAsset:
            return skill_query
        if cls is DabaiClue:
            return clue_query
        return MagicMock()

    db = MagicMock()
    db.query.side_effect = query_side_effect

    project = SimpleNamespace(id="proj-1")
    assert reconcile_misseeded_protagonist_skills(db, project, "李夜") is True  # type: ignore[arg-type]
    db.delete.assert_called_once_with(asset)
    assert db.add.called
