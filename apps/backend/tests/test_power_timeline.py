"""power_timeline 聚合测试。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.routers.outline.helpers.power_timeline import (
    _build_chart_series,
    _build_realm_scale,
    _compute_rows,
)
from app.routers.outline.helpers.power_timeline_lanes import build_character_realm_lanes


def test_build_chart_series_protagonist_and_boss():
    rows = [
        {
            "volume_order": 1,
            "phase": "opening",
            "protagonist_realm_start": "筑基境初期",
            "protagonist_rank_start": 1,
            "protagonist_realm_end": "筑基境后期",
            "protagonist_rank_end": 1,
            "boss_realm": "金丹境中期",
            "boss_major_rank": 2,
            "boss_effective_score": 2.2,
            "boss_name": "反派甲",
        },
    ]
    chart = _build_chart_series(rows)
    assert len(chart["protagonist"]) == 2
    assert len(chart["boss"]) == 1
    assert chart["boss"][0]["boss_name"] == "反派甲"


def test_character_lanes_include_protagonist_and_boss():
    project = SimpleNamespace(extra={"antagonist_ladder": []})
    rows = [
        {
            "volume_order": 1,
            "protagonist_realm_start": "筑基境",
            "protagonist_rank_start": 1,
            "protagonist_realm_end": "筑基境圆满",
            "protagonist_rank_end": 1,
            "boss_name": "反派甲",
            "boss_character_id": "boss-1",
            "boss_realm": "金丹境",
            "boss_major_rank": 2,
        },
    ]
    name_to_rank = {"筑基境": 1, "金丹境": 2}

    def rank_for_label(label, mapping):
        return mapping.get((label or "").strip())

    protag = SimpleNamespace(
        id="p1", name="主角", role="protagonist", character_tier="core",
        extra={}, current_realm=None, realm_rank=None,
    )
    boss = SimpleNamespace(
        id="boss-1", name="反派甲", role="antagonist", character_tier="arc",
        extra={}, current_realm=None, realm_rank=None,
    )
    lanes = build_character_realm_lanes(
        project, [protag, boss], rows, name_to_rank, rank_for_label,
    )
    names = {ln["display_name"] for ln in lanes}
    assert "主角" in names
    assert "反派甲" in names
