"""全书章号索引（跨卷累计）。"""

from __future__ import annotations

from typing import Any


def build_global_chapter_index(
    db: Any,
    project_id: Any,
) -> tuple[dict[str, int], int]:
    """构建 chapter_plan.id → 全书章号（1-based）映射。

    无子章的卷按 planned_chapters 占位推进游标，供 RP/CM 卷前规划校验。

    Returns:
        (node_id_str -> global_chapter_number, max_global_chapter)
    """
    from app.models import OutlineNode

    volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order.asc())
        .all()
    )

    node_to_global: dict[str, int] = {}
    cursor = 1

    for vol in volumes:
        children = (
            db.query(OutlineNode)
            .filter(
                OutlineNode.parent_id == vol.id,
                OutlineNode.node_type == "chapter_plan",
            )
            .order_by(OutlineNode.sort_order.asc())
            .all()
        )
        if children:
            base = cursor
            for ch in children:
                g = base + int(ch.sort_order or 0)
                node_to_global[str(ch.id)] = g
            cursor = max(node_to_global.values()) + 1
        else:
            planned = int((vol.extra or {}).get("planned_chapters") or 30)
            cursor += planned

    max_global = max(node_to_global.values()) if node_to_global else max(0, cursor - 1)
    return node_to_global, max_global


def global_for_volume_chapter(
    volume_sort_order: int,
    chapter_sort_order: int,
    volume_starts: dict[int, int],
) -> int:
    """由预计算的卷起始章号得到全书章号。"""
    start = volume_starts.get(volume_sort_order, 1)
    return start + int(chapter_sort_order or 0)


def build_volume_start_map(
    db: Any,
    project_id: Any,
) -> dict[int, int]:
    """卷 sort_order → 该卷第 1 章的全书章号。"""
    from app.models import OutlineNode

    volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order.asc())
        .all()
    )
    starts: dict[int, int] = {}
    cursor = 1
    for vol in volumes:
        idx = int(vol.sort_order or 0)
        starts[idx] = cursor
        children = (
            db.query(OutlineNode)
            .filter(
                OutlineNode.parent_id == vol.id,
                OutlineNode.node_type == "chapter_plan",
            )
            .count()
        )
        planned = int((vol.extra or {}).get("planned_chapters") or 30)
        span = children if children else planned
        cursor += span
    return starts
