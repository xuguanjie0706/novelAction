from app.services.outline_planning import (
    MIN_CHAPTERS_PER_VOLUME,
    TARGET_CHAPTERS_PER_VOLUME,
    TARGET_WORDS_PER_CHAPTER,
    WORD_ESTIMATE_RANGE,
    chunk_by_volume,
    normalize_chapter_count,
    normalize_volume_plan,
    target_total_chapters,
)


def test_normalize_chapter_count_rounds_to_thirty_chapter_units():
    assert normalize_chapter_count(15) == MIN_CHAPTERS_PER_VOLUME
    assert normalize_chapter_count(44) == MIN_CHAPTERS_PER_VOLUME
    assert normalize_chapter_count(45) == 60
    assert normalize_chapter_count(46) == 60
    assert normalize_chapter_count(75) == 90
    assert normalize_chapter_count(None) == MIN_CHAPTERS_PER_VOLUME


def test_scale_targets_match_long_novel_word_counts():
    assert TARGET_WORDS_PER_CHAPTER == 2300
    assert WORD_ESTIMATE_RANGE == (2200, 2400)
    assert target_total_chapters("short") == 360
    assert target_total_chapters("auto") == 540
    assert target_total_chapters("medium") == 540
    assert target_total_chapters("long") == 660


def test_medium_plan_is_lifted_to_nine_sixty_chapter_volumes():
    volumes = [{"title": "试炼", "planned_chapters": 15}]

    normalized = normalize_volume_plan(volumes, "medium")

    assert len(normalized) == 9
    assert sum(v["planned_chapters"] for v in normalized) == 540
    assert {v["planned_chapters"] for v in normalized} == {TARGET_CHAPTERS_PER_VOLUME}
    assert normalized[0]["title"] == "试炼（一）"
    assert volumes == [{"title": "试炼", "planned_chapters": 15}]


def test_long_plan_preserves_existing_large_plan():
    volumes = [
        {"title": "入局", "planned_chapters": 300},
        {"title": "破局", "planned_chapters": 360},
    ]

    normalized = normalize_volume_plan(volumes, "long")

    assert len(normalized) == 11
    assert sum(v["planned_chapters"] for v in normalized) == 660
    assert {v["planned_chapters"] for v in normalized} == {TARGET_CHAPTERS_PER_VOLUME}


def test_chunk_by_volume_splits_chapters_into_sixty_chapter_groups():
    chapters = list(range(65))

    groups = list(chunk_by_volume(chapters))

    assert [len(group) for group in groups] == [60, 5]
