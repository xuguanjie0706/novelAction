"""fanqie_axis — 修仙类型公式判定单测。"""
from app.services.bootstrap.fanqie_axis import XIANXIA_GENRE_ARCHETYPE, is_xianxia_archetype


def test_xianxia_official_archetype():
    assert is_xianxia_archetype({"fanqie_positioning": {"genre_archetype": XIANXIA_GENRE_ARCHETYPE}})


def test_xianxia_keyword_in_archetype():
    assert is_xianxia_archetype({"fanqie_positioning": {"genre_archetype": "仙侠逆袭流"}})


def test_social_archetype_not_xianxia():
    assert not is_xianxia_archetype({"fanqie_positioning": {"genre_archetype": "赘婿打脸流"}})


def test_manual_overrides_ignored():
    """不接受 cultivation_axis / fanqie_axis_kind / positioning 回退。"""
    assert not is_xianxia_archetype({
        "cultivation_axis": True,
        "fanqie_axis_kind": "cultivation",
        "positioning": {"genre_archetype": "修仙打脸流"},
    })
    assert not is_xianxia_archetype({"fanqie_positioning": {}})
