"""章级境界轴（方向1）纯逻辑回归测试。

覆盖：卷内插值、显式里程碑锚点取 max、无境界体系/无锚点降级、linter 暴跳与倒退检测。
expected_realm_for_chapter 仅在 name_to_rank=None 时访问 db；显式传入即可脱库测。
"""
from types import SimpleNamespace

from app.services.ai.realm_axis import (
    _interp_rank,
    _milestone_rank,
    expected_realm_for_chapter,
    lint_realm_axis,
)

# 斗破式境界阶梯：name -> rank
NAME_TO_RANK = {
    "斗者": 3, "斗师": 4, "大斗师": 5, "斗灵": 6, "斗王": 7, "斗皇": 8, "斗宗": 9,
    "六星斗者": 36, "九星斗者": 39,  # 细分星级（更长名优先命中）
}


def _make_chapter(node):
    return SimpleNamespace(outline_node=node)


def _volume(start_rank, end_rank, chapter_plans):
    vol = SimpleNamespace(
        node_type="volume",
        sort_order=0,
        parent=None,
        extra={"protagonist_realm_start_rank": start_rank, "protagonist_realm_end_rank": end_rank},
        children=chapter_plans,
    )
    for cp in chapter_plans:
        cp.parent = vol
    return vol


def _chapter_plan(idx, power_milestone=""):
    return SimpleNamespace(
        id=f"cp{idx}",
        node_type="chapter_plan",
        sort_order=idx,
        power_milestone=power_milestone,
        children=[],
        parent=None,
    )


# ── 纯插值 ────────────────────────────────────────────────
def test_interp_monotonic_and_bounds():
    ranks = [_interp_rank(3, 9, p, 30) for p in range(30)]
    assert ranks[0] == 3 and ranks[-1] == 9
    assert all(ranks[i] <= ranks[i + 1] for i in range(len(ranks) - 1))


def test_interp_single_chapter_volume_hits_end():
    assert _interp_rank(3, 9, 0, 1) == 9


# ── 里程碑锚点 ────────────────────────────────────────────
def test_milestone_requires_progression_verb():
    node_no_verb = SimpleNamespace(power_milestone="葛叶展现斗灵实力")
    node_verb = SimpleNamespace(power_milestone="主角突破到斗灵")
    assert _milestone_rank(node_no_verb, NAME_TO_RANK) is None
    assert _milestone_rank(node_verb, NAME_TO_RANK) == 6


# ── 端到端：每章都有应有境界 ──────────────────────────────
def test_expected_realm_fills_gap_without_milestone():
    plans = [_chapter_plan(i) for i in range(10)]
    vol = _volume(3, 8, plans)
    project = SimpleNamespace(id="p")
    # 第 5 章没有里程碑，仍应有确定性应有境界
    label, rank = expected_realm_for_chapter(None, project, _make_chapter(plans[5]), NAME_TO_RANK)
    assert rank is not None and 3 <= rank <= 8
    assert label  # 能映射到境界名


def test_expected_realm_milestone_anchor_takes_max():
    plans = [_chapter_plan(i) for i in range(10)]
    plans[2].power_milestone = "提前突破到斗王"  # rank 7，远高于第3章插值
    vol = _volume(3, 8, plans)
    project = SimpleNamespace(id="p")
    label, rank = expected_realm_for_chapter(None, project, _make_chapter(plans[2]), NAME_TO_RANK)
    assert rank == 7  # 取 max(插值, 里程碑)，但不越卷末上限 8


def test_expected_realm_caps_at_volume_end():
    plans = [_chapter_plan(i) for i in range(5)]
    plans[0].power_milestone = "突破到斗宗"  # rank 9 > 卷末 8
    vol = _volume(3, 8, plans)
    project = SimpleNamespace(id="p")
    _, rank = expected_realm_for_chapter(None, project, _make_chapter(plans[0]), NAME_TO_RANK)
    assert rank == 8  # 被卷末上限钳住


def test_expected_realm_none_without_power_system():
    plans = [_chapter_plan(0)]
    _volume(3, 8, plans)
    project = SimpleNamespace(id="p")
    label, rank = expected_realm_for_chapter(None, project, _make_chapter(plans[0]), {})
    assert (label, rank) == (None, None)


def test_no_volume_bounds_falls_back_to_milestone():
    """番茄/同人线：卷级 rank 缺失时退回 power_milestone 显式锚点（方向2/3 不失效）。"""
    plans = [_chapter_plan(0, power_milestone="主角突破到斗灵")]
    vol = SimpleNamespace(node_type="volume", sort_order=0, parent=None, extra={}, children=plans)
    plans[0].parent = vol
    project = SimpleNamespace(id="p")
    label, rank = expected_realm_for_chapter(None, project, _make_chapter(plans[0]), NAME_TO_RANK)
    assert rank == 6  # 斗灵，来自里程碑回退


def test_no_volume_bounds_no_milestone_returns_none():
    plans = [_chapter_plan(0, power_milestone="本章主角与人对峙")]  # 无突破动词
    vol = SimpleNamespace(node_type="volume", sort_order=0, parent=None, extra={}, children=plans)
    plans[0].parent = vol
    project = SimpleNamespace(id="p")
    assert expected_realm_for_chapter(None, project, _make_chapter(plans[0]), NAME_TO_RANK) == (None, None)


# ── linter ───────────────────────────────────────────────
def test_lint_detects_regression_and_jump():
    axis = [
        {"expected_rank": 3, "sort_order": 1},
        {"expected_rank": 5, "sort_order": 2},  # +2 ok
        {"expected_rank": 4, "sort_order": 3},  # 倒退
        {"expected_rank": 8, "sort_order": 4},  # 暴跳 +4
    ]
    issues = lint_realm_axis(axis)
    types = {i["type"] for i in issues}
    assert "realm_axis_regression" in types
    assert "realm_axis_jump" in types


def test_lint_clean_axis_no_issues():
    axis = [{"expected_rank": r, "sort_order": i + 1} for i, r in enumerate([3, 3, 4, 5, 6])]
    assert lint_realm_axis(axis) == []
