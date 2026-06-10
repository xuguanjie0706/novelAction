"""dabai 章纲节点解析 — 主链路 Project/Chapter/OutlineNode。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Chapter, OutlineNode


def resolve_chapter_plan(
    db: Session,
    project_id: str,
    chapter: Chapter,
) -> OutlineNode | None:
    """解析章节对应的 chapter_plan 节点。

    优先 ``chapter.outline_node_id``；否则按 ``sort_order`` 对齐章序。
    """
    if chapter.outline_node_id:
        plan = (
            db.query(OutlineNode)
            .filter(
                OutlineNode.id == chapter.outline_node_id,
                OutlineNode.project_id == project_id,
                OutlineNode.node_type == "chapter_plan",
            )
            .first()
        )
        if plan:
            return plan

    sort_order = int(chapter.sort_order or 0)
    return (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "chapter_plan",
            OutlineNode.sort_order == sort_order,
        )
        .first()
    )


def chapter_display_number(chapter: Chapter) -> int:
    """全书章序号（1-based）。"""
    return int(chapter.sort_order or 0) + 1
