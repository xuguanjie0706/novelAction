"""
realm_axis.py — 章级主角境界轴（方向1：治本，单一权威）

设计动机：
  此前主角境界有两个滞后真相源（正文领先、复盘记录滞后），质检拿滞后记录判新正文，
  每章误报。方向2/3 用「章纲 power_milestone」做了 floor，但**没有里程碑的章节仍是空白**，
  只能回退到滞后记录。本模块补上空白：

  以「卷级主角境界起止 rank（apply_volume_protagonist_fields 已落库的
  protagonist_realm_start_rank / end_rank）」为锚，按章在卷内的位置**线性插值**，
  让每一章都有一个确定性的「应有境界 rank」。显式 power_milestone 突破点作为锚点取 max。

  这条轴是写章、质检共用的**单一权威基准**：
  - 写章：注入「本章主角应有境界」硬目标。
  - 质检：以轴为基准判超纲/滞后，而非 current_realm。
  - realm_plan_floor：用轴推进 current_realm（覆盖无里程碑章节）。

设计约束：
- 无境界体系（name_to_rank 空）时全部返回空，特性自动失效，不打扰都市/言情书。
- 全程只读，不写库；落库由 realm_plan_floor 负责。
"""
from __future__ import annotations

from typing import Any

from app.models import OutlineNode, PowerSystem
from app.routers.outline.helpers.realm_timeline import (
    _rank_for_realm_label,
    _realm_display_name_for_rank,
)
from app.routers.outline.helpers.realm_whitelist import build_realm_rank_map

# 与 realm_plan_floor 一致：power_milestone 须含进阶动词才视作主角突破锚点。
_PROGRESSION_MARKERS = (
    "突破", "晋级", "进阶", "跨入", "迈入", "突入", "修为", "境界提升",
    "升至", "踏入", "臻至", "晋升",
)


def build_name_to_rank(db: Any, project_id: Any) -> dict[str, int]:
    systems = db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()
    name_to_rank, _, _ = build_realm_rank_map(systems)
    return name_to_rank or {}


def _find_volume_node(node: OutlineNode) -> OutlineNode | None:
    """从 chapter_plan 节点向上找到所属 volume 节点（容忍 volume→arc→chapter_plan 三层）。"""
    cur = node
    guard = 0
    while cur is not None and guard < 8:
        if (cur.node_type or "") == "volume":
            return cur
        cur = cur.parent
        guard += 1
    return None


def _ordered_chapter_plans(db: Any, volume_node: OutlineNode) -> list[OutlineNode]:
    """递归收集 volume 下所有 chapter_plan 节点，按 sort_order 排序。"""
    out: list[OutlineNode] = []
    stack = [volume_node]
    guard = 0
    while stack and guard < 5000:
        guard += 1
        cur = stack.pop()
        for child in sorted(cur.children or [], key=lambda n: n.sort_order or 0):
            if (child.node_type or "") == "chapter_plan":
                out.append(child)
            else:
                stack.append(child)
    out.sort(key=lambda n: n.sort_order or 0)
    return out


def _volume_rank_bounds(volume_node: OutlineNode) -> tuple[int, int] | None:
    ex = volume_node.extra if isinstance(volume_node.extra, dict) else {}
    s = ex.get("protagonist_realm_start_rank")
    e = ex.get("protagonist_realm_end_rank")
    if not isinstance(s, int) or not isinstance(e, int):
        return None
    if e < s:
        e = s
    return s, e


def _milestone_rank(node: OutlineNode, name_to_rank: dict[str, int]) -> int | None:
    milestone = (getattr(node, "power_milestone", None) or "").strip()
    if not milestone or not any(m in milestone for m in _PROGRESSION_MARKERS):
        return None
    r = _rank_for_realm_label(milestone, name_to_rank)
    return r if isinstance(r, int) and r > 0 else None


def _milestone_only(node: OutlineNode, name_to_rank: dict[str, int]) -> tuple[str | None, int | None]:
    """卷级境界 rank 缺失时（番茄/同人线常见，卷骨架早于 power 体系生成）的回退：

    仅凭本章显式 power_milestone 突破点给出应有境界，无锚点则不约束。
    保证这些线仍享有方向2/3 的「计划境界 floor」，不因缺卷界而完全失效。
    """
    r = _milestone_rank(node, name_to_rank)
    if r is None:
        return None, None
    return _realm_display_name_for_rank(r, name_to_rank), r


def _interp_rank(start_rank: int, end_rank: int, pos: int, total: int) -> int:
    """卷内第 pos（0-based）章 / 共 total 章 的线性插值 rank（向最近取整，非递减）。"""
    if total <= 1:
        return end_rank
    frac = (pos + 1) / total
    val = start_rank + (end_rank - start_rank) * frac
    return max(start_rank, min(end_rank, round(val)))


def expected_realm_for_chapter(
    db: Any, project: Any, chapter: Any, name_to_rank: dict[str, int] | None = None
) -> tuple[str | None, int | None]:
    """返回本章主角「应有境界」(label, rank)。无境界体系 / 无章纲锚点时返回 (None, None)。"""
    if name_to_rank is None:
        name_to_rank = build_name_to_rank(db, project.id)
    if not name_to_rank:
        return None, None
    node = getattr(chapter, "outline_node", None)
    if node is None:
        return None, None
    volume = _find_volume_node(node)
    bounds = _volume_rank_bounds(volume) if volume is not None else None
    if bounds is None:
        # 卷级 rank 缺失（番茄/同人线）：退回 power_milestone 显式锚点，不因此完全失效。
        return _milestone_only(node, name_to_rank)
    start_rank, end_rank = bounds

    plans = _ordered_chapter_plans(db, volume)
    pos, total = 0, len(plans)
    if plans:
        ids = [str(p.id) for p in plans]
        try:
            pos = ids.index(str(node.id))
        except ValueError:
            pos = 0
    else:
        total = int((volume.extra or {}).get("planned_chapters") or 1)

    rank = _interp_rank(start_rank, end_rank, pos, max(1, total))

    # 显式突破里程碑作为锚点：取 max（计划提前突破合法），但不越过卷末上限。
    ms_rank = _milestone_rank(node, name_to_rank)
    if ms_rank is not None:
        rank = max(rank, min(ms_rank, end_rank))

    label = _realm_display_name_for_rank(rank, name_to_rank)
    return label, rank


def build_chapter_realm_axis(db: Any, project: Any) -> list[dict]:
    """构建全书章级境界轴（仅含已展开的 chapter_plan），供可视化 / linter。"""
    name_to_rank = build_name_to_rank(db, project.id)
    if not name_to_rank:
        return []
    volumes = (
        db.query(OutlineNode)
        .filter(OutlineNode.project_id == project.id, OutlineNode.node_type == "volume")
        .order_by(OutlineNode.sort_order)
        .all()
    )
    axis: list[dict] = []
    for vi, vol in enumerate(volumes):
        bounds = _volume_rank_bounds(vol)
        if bounds is None:
            continue
        start_rank, end_rank = bounds
        plans = _ordered_chapter_plans(db, vol)
        total = max(1, len(plans) or int((vol.extra or {}).get("planned_chapters") or 1))
        for pos, node in enumerate(plans):
            rank = _interp_rank(start_rank, end_rank, pos, total)
            ms = _milestone_rank(node, name_to_rank)
            if ms is not None:
                rank = max(rank, min(ms, end_rank))
            axis.append({
                "volume_index": vi,
                "chapter_node_id": str(node.id),
                "sort_order": node.sort_order or 0,
                "expected_rank": rank,
                "expected_label": _realm_display_name_for_rank(rank, name_to_rank),
                "has_milestone": ms is not None,
            })
    axis.sort(key=lambda a: a["sort_order"])
    return axis


def lint_realm_axis(axis: list[dict]) -> list[dict]:
    """校验境界轴：非递减 + 单章跳变不超过 2 rank（防一章暴跳）。"""
    issues: list[dict] = []
    prev = None
    for a in axis:
        r = a.get("expected_rank")
        if not isinstance(r, int):
            continue
        if prev is not None:
            if r < prev["expected_rank"]:
                issues.append({
                    "type": "realm_axis_regression",
                    "sort_order": a["sort_order"],
                    "msg": f"第{a['sort_order']}章应有境界 rank {r} 低于前章 {prev['expected_rank']}（境界倒退）",
                })
            elif r - prev["expected_rank"] > 2:
                issues.append({
                    "type": "realm_axis_jump",
                    "sort_order": a["sort_order"],
                    "msg": f"第{a['sort_order']}章应有境界 rank 较前章暴跳 {r - prev['expected_rank']}（>2，疑似规划跳级）",
                })
        prev = a
    return issues
