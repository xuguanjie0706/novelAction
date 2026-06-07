"""章纲写入防护：展开锁、sort_order 去重、占用检测。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import OutlineNode

logger = logging.getLogger(__name__)

EXPAND_LOCK_KEY = "expand_in_progress"
EXPAND_LOCK_AT_KEY = "expand_in_progress_at"
# 超过该秒数视为僵死锁，允许新请求接管
EXPAND_LOCK_STALE_SEC = 45 * 60


def existing_chapter_sort_orders(db: Session, volume_id) -> set[int]:
    """卷下已占用的 chapter_plan sort_order 集合（0-based）。"""
    rows = (
        db.query(OutlineNode.sort_order)
        .filter(
            OutlineNode.parent_id == volume_id,
            OutlineNode.node_type == "chapter_plan",
        )
        .all()
    )
    return {int(r[0]) for r in rows if r[0] is not None}


def count_unique_chapter_plans(nodes: list[OutlineNode]) -> int:
    """按 sort_order 去重后的章纲数量。"""
    return len({n.sort_order for n in nodes})


def dedupe_volume_chapter_plans(db: Session, volume_id) -> int:
    """同卷同 sort_order 仅保留最新一条，删除其余重复节点。

    Returns:
        删除的节点数。
    """
    nodes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.parent_id == volume_id,
            OutlineNode.node_type == "chapter_plan",
        )
        .order_by(OutlineNode.sort_order, OutlineNode.created_at)
        .all()
    )
    by_order: dict[int, list[OutlineNode]] = {}
    for node in nodes:
        by_order.setdefault(int(node.sort_order or 0), []).append(node)

    deleted = 0
    for group in by_order.values():
        if len(group) <= 1:
            continue
        group.sort(
            key=lambda n: (
                n.updated_at or n.created_at or datetime.min.replace(tzinfo=timezone.utc),
                str(n.id),
            ),
            reverse=True,
        )
        for dup in group[1:]:
            db.delete(dup)
            deleted += 1
    if deleted:
        db.commit()
        logger.info("dedupe_volume_chapter_plans volume=%s removed=%d", volume_id, deleted)
    return deleted


def volume_expand_lock_active(volume: OutlineNode) -> bool:
    """卷是否处于展开中（未过期锁）。"""
    extra = volume.extra if isinstance(volume.extra, dict) else {}
    if not extra.get(EXPAND_LOCK_KEY):
        return False
    raw_at = extra.get(EXPAND_LOCK_AT_KEY)
    if not raw_at:
        return True
    try:
        started = datetime.fromisoformat(str(raw_at).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - started).total_seconds()
        return age < EXPAND_LOCK_STALE_SEC
    except (TypeError, ValueError):
        return True


def set_volume_expand_lock(db: Session, volume: OutlineNode) -> None:
    """标记卷正在展开章纲。"""
    extra = dict(volume.extra or {})
    extra[EXPAND_LOCK_KEY] = True
    extra[EXPAND_LOCK_AT_KEY] = datetime.now(timezone.utc).isoformat()
    volume.extra = extra
    flag_modified(volume, "extra")
    db.commit()


def clear_volume_expand_lock(db: Session, volume: OutlineNode) -> None:
    """解除卷展开锁。"""
    extra = dict(volume.extra or {})
    if not extra.pop(EXPAND_LOCK_KEY, None) and not extra.pop(EXPAND_LOCK_AT_KEY, None):
        return
    volume.extra = extra
    flag_modified(volume, "extra")
    db.commit()


def parent_has_chapter_plans(db: Session, parent_id) -> bool:
    """父节点下是否已有 chapter_plan。"""
    return (
        db.query(OutlineNode.id)
        .filter(
            OutlineNode.parent_id == parent_id,
            OutlineNode.node_type == "chapter_plan",
        )
        .limit(1)
        .first()
        is not None
    )
