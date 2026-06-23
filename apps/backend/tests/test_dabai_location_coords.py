"""dabai 位置台账坐标（A 档）单测。"""
from app.services.dabai.lab_location_coords import (
    default_location_change_reason,
    locations_equivalent,
    normalize_ledger_location,
    prose_has_ledger_location_dot,
    split_ledger_location,
)


def test_split_ledger_location():
    assert split_ledger_location("鬼市地宫·废弃矿道") == ("鬼市地宫", "废弃矿道")
    assert split_ledger_location("废弃矿道") == ("", "废弃矿道")


def test_normalize_inherits_region_from_prev():
    out = normalize_ledger_location(
        "废弃矿道",
        prev_location="执事堂广场·生死擂台",
    )
    assert out == "执事堂广场·废弃矿道"


def test_normalize_keeps_existing_dot():
    assert normalize_ledger_location("鬼市地宫·边缘矿道") == "鬼市地宫·边缘矿道"


def test_locations_equivalent_same_region():
    assert locations_equivalent("鬼市地宫·矿道", "鬼市地宫·废弃矿道") is True
    assert locations_equivalent("执事堂·擂台", "万宝阁·大堂") is False


def test_default_reason_unchanged():
    assert default_location_change_reason("A·b", "A·c", "") == "本章未离开当前区域"
    assert default_location_change_reason("A·b", "X·y", "沿矿道潜入") == "沿矿道潜入"


def test_prose_ledger_dot_detection():
    assert prose_has_ledger_location_dot("他踏入鬼市地宫·废弃矿道") is True
    assert prose_has_ledger_location_dot("他踏入废弃矿道深处") is False
