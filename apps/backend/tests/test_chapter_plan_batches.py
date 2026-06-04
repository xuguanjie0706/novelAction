"""chapter_plan_batches 单元测试。"""
from app.services.bootstrap.chapter_plan_batches import (
    chapter_plan_batch_ranges,
    normalize_volume_planned_chapters,
)


def test_normalize_volume_planned_chapters_respects_volume_extra():
    assert normalize_volume_planned_chapters(50) == 50
    assert normalize_volume_planned_chapters(60) == 60
    assert normalize_volume_planned_chapters(45) == 45
    assert normalize_volume_planned_chapters(14) == 30
    assert normalize_volume_planned_chapters(90) == 80
    assert normalize_volume_planned_chapters(None) == 30


def test_chapter_plan_batch_ranges_single_shot_when_within_chunk():
    # ≤30 章且预算足够时整卷一次
    assert chapter_plan_batch_ranges(25, 65536) == [(1, 25)]
    assert chapter_plan_batch_ranges(30, 65536) == [(1, 30)]


def test_chapter_plan_batch_ranges_splits_over_30_even_with_large_budget():
    # 单批硬上限 30 章；50/60 章即使 token 充足也拆批，降低 JSON 解析失败率
    assert chapter_plan_batch_ranges(50, 65536) == [(1, 30), (31, 50)]
    assert chapter_plan_batch_ranges(60, 65536) == [(1, 30), (31, 60)]


def test_chapter_plan_batch_ranges_splits_30_plus_remainder():
    # 小预算：50 章 → 1-30 + 31-50
    assert chapter_plan_batch_ranges(50, 16384) == [(1, 30), (31, 50)]
    assert chapter_plan_batch_ranges(80, 16384) == [(1, 30), (31, 60), (61, 80)]
