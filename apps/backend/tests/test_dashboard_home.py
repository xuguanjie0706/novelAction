"""Tests for dashboard.compute_weekly_writing_stats (pure function)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.routers.dashboard import compute_weekly_writing_stats


TODAY = date(2026, 5, 7)  # Thursday → weekday()=3 → '四'


def _dt(day: date, hour: int = 12) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0)


def test_empty_input_returns_zeros_with_seven_day_skeleton():
    """无任何 ChapterVersion → 全 0，但 week 仍是 7 项骨架。"""
    out = compute_weekly_writing_stats([], TODAY)

    assert out["today_words"] == 0
    assert out["streak_days"] == 0
    assert out["writing_days"] == 0
    assert out["average_words"] == 0
    assert len(out["week"]) == 7
    # 每项 height 至少为最小可见高度 4
    assert all(item["height"] == 4 for item in out["week"])
    # 第一项是 7 天前，最后一项是今天
    assert out["week"][0]["date"] == (TODAY - timedelta(days=6)).isoformat()
    assert out["week"][-1]["date"] == TODAY.isoformat()


def test_single_chapter_three_snapshots_increment_diff():
    """同一章三条快照 0→500→1200，差分得到 500 + 700 = 1200，全部落今天。"""
    rows = [
        ("ch-1", _dt(TODAY, 9), 500),
        ("ch-1", _dt(TODAY, 11), 1200),
    ]
    out = compute_weekly_writing_stats(rows, TODAY)

    assert out["today_words"] == 1200
    assert out["streak_days"] == 1
    assert out["writing_days"] == 1
    assert out["average_words"] == 1200  # 1200 // 1
    # 今天柱子 height 为最大 78（因为唯一非零项即最大）
    assert out["week"][-1]["words"] == 1200
    assert out["week"][-1]["height"] == 78


def test_streak_counts_only_consecutive_days_back_from_today():
    """昨天 + 今天 + 三天前各写了一些；连续天数应该是 2（今天+昨天，三天前断了）。"""
    yesterday = TODAY - timedelta(days=1)
    three_days_ago = TODAY - timedelta(days=3)
    rows = [
        ("ch-a", _dt(three_days_ago), 300),
        ("ch-b", _dt(yesterday), 200),
        ("ch-c", _dt(TODAY), 100),
    ]
    out = compute_weekly_writing_stats(rows, TODAY)

    assert out["today_words"] == 100
    assert out["streak_days"] == 2
    assert out["writing_days"] == 3  # 7 天内有 3 天写作
    # 平均 = (300 + 200 + 100) / 3 = 200
    assert out["average_words"] == 200


def test_negative_diff_does_not_subtract_from_today():
    """同章字数回退（500→300）差为负，必须截 0，不能从「今日字数」中扣。"""
    rows = [
        ("ch-1", _dt(TODAY, 9), 500),
        ("ch-1", _dt(TODAY, 11), 300),
    ]
    out = compute_weekly_writing_stats(rows, TODAY)
    # 第一条记 500（视为从 0 写到 500），第二条 -200 → 截 0
    assert out["today_words"] == 500


def test_today_no_writing_yields_streak_zero():
    """今天没写，即使昨天写了，连续天数也应为 0。"""
    yesterday = TODAY - timedelta(days=1)
    rows = [("ch-1", _dt(yesterday), 800)]
    out = compute_weekly_writing_stats(rows, TODAY)

    assert out["today_words"] == 0
    assert out["streak_days"] == 0
    assert out["writing_days"] == 1


def test_multi_chapter_diffs_dont_cross_chapters():
    """两章独立差分：A 0→1000，B 0→500，今天总增量 1500。"""
    rows = [
        ("ch-a", _dt(TODAY, 9), 1000),
        ("ch-b", _dt(TODAY, 10), 500),
    ]
    out = compute_weekly_writing_stats(rows, TODAY)
    assert out["today_words"] == 1500


def test_week_height_proportional_to_max_day():
    """柱状图 height 按全周最大值归一；非最大日按比例 + 最小 4。"""
    yesterday = TODAY - timedelta(days=1)
    rows = [
        ("ch-a", _dt(yesterday), 1000),  # 昨天 1000
        ("ch-b", _dt(TODAY), 500),       # 今天 500
    ]
    out = compute_weekly_writing_stats(rows, TODAY)

    # 找到「昨天」和「今天」两项
    week_by_date = {item["date"]: item for item in out["week"]}
    y_item = week_by_date[yesterday.isoformat()]
    t_item = week_by_date[TODAY.isoformat()]

    assert y_item["words"] == 1000
    assert y_item["height"] == 78        # 全周最大
    assert t_item["words"] == 500
    # 500/1000 * 78 = 39
    assert t_item["height"] == 39
