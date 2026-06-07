"""
番茄卷纲按需展开：补全章纲区间解析、旧数据 sort_order 迁移。
（存量 extra.opening_5chapters 仍可物化 1–5 章，新流程不再写入该字段。）
"""
from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import OutlineNode, Project
from app.services.bootstrap.chapter_plan_guard import (
    count_unique_chapter_plans,
    dedupe_volume_chapter_plans,
)
from app.services.bootstrap.fanqie_normalize import (
    is_fanqie_project,
    upsert_opening_chapter_plans,
)


def materialize_opening_chapter_plans(
    db: Session,
    project: Project,
    volume: OutlineNode,
    ctx: dict | None = None,
) -> int:
    """从 extra.opening_5chapters 物化 1–5 章 chapter_plan（展开章纲时调用）。"""
    ctx = ctx or {}
    opening = ctx.get("opening_5chapters") or (project.extra or {}).get("opening_5chapters")
    if not isinstance(opening, dict) or not opening:
        return 0
    upsert_opening_chapter_plans(db, project, opening, ctx)
    return (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.parent_id == volume.id,
            OutlineNode.node_type == "chapter_plan",
            OutlineNode.sort_order < 5,
        )
        .count()
    )


def chapter_index_from_node(node: OutlineNode) -> int:
    """卷内章序（1-based）；sort_order 统一为 0-based。"""
    return node.sort_order + 1


def normalize_legacy_opening_sort_orders(nodes: list[OutlineNode]) -> None:
    """将旧番茄开局章 sort_order 从 1–5 迁移为 0–4。"""
    opening = [
        n for n in nodes
        if (n.extra or {}).get("bootstrap_fanqie")
        and not (n.extra or {}).get("lazy_expanded")
    ]
    if not opening:
        return
    orders = [n.sort_order for n in opening]
    if min(orders) >= 1 and max(orders) <= 5:
        for n in opening:
            n.sort_order = n.sort_order - 1
            flag_modified(n, "extra")


def _existing_chapter_plans(db: Session, volume_id) -> list[OutlineNode]:
    return (
        db.query(OutlineNode)
        .filter(
            OutlineNode.parent_id == volume_id,
            OutlineNode.node_type == "chapter_plan",
        )
        .order_by(OutlineNode.sort_order)
        .all()
    )


def prepare_volume_chapter_expand(
    db: Session,
    project: Project,
    volume: OutlineNode,
    ctx: dict,
    *,
    force: bool,
) -> tuple[int, int, list[OutlineNode]] | None:
    """
    解析按卷展开章纲的起止章与种子节点。

    Returns:
        (chapter_from, chapter_to, seed_nodes)；若已满卷返回 None（应 409）。
    """
    from app.services.bootstrap.chapter_plan_batches import normalize_volume_planned_chapters

    if force:
        db.query(OutlineNode).filter(
            OutlineNode.parent_id == volume.id,
            OutlineNode.node_type == "chapter_plan",
        ).delete(synchronize_session=False)
        db.commit()
    else:
        dedupe_volume_chapter_plans(db, volume.id)

    planned = normalize_volume_planned_chapters(
        (volume.extra or {}).get("planned_chapters"),
        default=50 if is_fanqie_project(project, ctx) else 30,
    )
    existing = _existing_chapter_plans(db, volume.id)
    if existing:
        normalize_legacy_opening_sort_orders(existing)
        db.commit()
        existing = _existing_chapter_plans(db, volume.id)

    if existing and count_unique_chapter_plans(existing) >= planned and not force:
        return None

    if not existing:
        # 仅兼容存量 Bootstrap 写入的 opening_5chapters；新项目从第 1 章起由 AI 展开
        if (project.extra or {}).get("opening_5chapters"):
            materialize_opening_chapter_plans(db, project, volume, ctx)
            existing = _existing_chapter_plans(db, volume.id)
            if existing:
                max_ch = max(chapter_index_from_node(n) for n in existing)
                return max_ch + 1, planned, existing
        return 1, planned, existing

    max_ch = max(chapter_index_from_node(n) for n in existing)
    if max_ch >= planned:
        return None
    return max_ch + 1, planned, existing


def strip_volume_chapter_plans(db: Session, project: Project) -> int:
    """删除项目下全部 chapter_plan（保留卷纲与 extra.opening_5chapters）。"""
    deleted = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.node_type == "chapter_plan",
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
