"""全书故事时间线聚合（纯函数）。"""
from app.routers.outline.helpers.story_timeline import parse_chapter_range


def test_parse_chapter_range_variants():
    assert parse_chapter_range("第1-30章") == (1, 30)
    assert parse_chapter_range("1~50") == (1, 50)
    assert parse_chapter_range("第12章") == (12, 12)
    assert parse_chapter_range("全书") is None
    assert parse_chapter_range("") is None
