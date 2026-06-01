"""debrief_character_sync — 从 chapter_index 补全 character_updates。"""
from app.services.ai.debrief_character_sync import (
    merge_character_updates_for_debrief,
    supplement_character_updates_from_chapter_index,
)

_CHU = {
    "id": "48e5146e-c6ad-4f50-974e-32b010455844",
    "name": "楚惊羽",
    "current_realm": "聚火境三重",
    "current_location": "青阳城楚家破旧柴房",
    "current_status": "alive",
}


def test_supplement_realm_and_location_from_ch13_style_index():
    index = {
        "core_events": [
            "楚惊羽将庚金剑气转化为纯净火能，修为连破数重达到聚火境九重巅峰。",
            "禁制消散显现出上古火脉本源，楚惊羽正欲收取时遭遇偷袭。",
        ],
    }
    extra = supplement_character_updates_from_chapter_index([], index, [_CHU])
    assert len(extra) == 1
    assert extra[0]["character_id"] == _CHU["id"]
    assert "九重巅峰" in extra[0]["current_realm"]


def test_does_not_duplicate_when_llm_already_sent_update():
    index = {"core_events": ["楚惊羽达到聚火境九重巅峰。"]}
    existing = [{
        "character_id": _CHU["id"],
        "character_name": "楚惊羽",
        "current_realm": "聚火境九重巅峰",
    }]
    extra = supplement_character_updates_from_chapter_index(existing, index, [_CHU])
    assert extra == []


def test_merge_fills_missing_realm_on_partial_update():
    index = {"core_events": ["楚惊羽突破至聚火境九重巅峰，深入青阳火脉。"]}
    merged = merge_character_updates_for_debrief([], index, [_CHU])
    assert len(merged) == 1
    assert "九重巅峰" in merged[0]["current_realm"]
