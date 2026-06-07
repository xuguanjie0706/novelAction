"""章纲防重复：去重计数、展开锁。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import OutlineNode
from app.services.bootstrap.chapter_plan_guard import (
    count_unique_chapter_plans,
    volume_expand_lock_active,
)


def test_count_unique_chapter_plans():
    nodes = [
        OutlineNode(sort_order=0, node_type="chapter_plan", title="a"),
        OutlineNode(sort_order=0, node_type="chapter_plan", title="b"),
        OutlineNode(sort_order=1, node_type="chapter_plan", title="c"),
    ]
    assert count_unique_chapter_plans(nodes) == 2


def test_volume_expand_lock_active_when_set():
    vol = OutlineNode(
        node_type="volume",
        title="卷",
        extra={
            "expand_in_progress": True,
            "expand_in_progress_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert volume_expand_lock_active(vol)


def test_volume_expand_lock_inactive_when_stale():
    vol = OutlineNode(
        node_type="volume",
        title="卷",
        extra={
            "expand_in_progress": True,
            "expand_in_progress_at": (
                datetime.now(timezone.utc) - timedelta(hours=2)
            ).isoformat(),
        },
    )
    assert not volume_expand_lock_active(vol)
