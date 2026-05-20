"""Bootstrap 章纲 → Foreshadow 同步回归。"""

from __future__ import annotations

import uuid

from app.models import Foreshadow
from app.services.bootstrap.foreshadow_sync import _title_from_text


def test_foreshadow_constructor_accepts_extra():
    """模型须有 extra 列，避免 bootstrap 写库 TypeError。"""
    fs = Foreshadow(
        project_id=uuid.uuid4(),
        title="退婚真相",
        description="退婚真相",
        laid_chapter_number=3,
        status="open",
        foreshadow_type="hook",
        extra={
            "theme_note": "主角身世",
            "source_outline_node_id": str(uuid.uuid4()),
            "heat_log": [],
        },
    )
    assert fs.extra["theme_note"] == "主角身世"
    assert fs.extra["heat_log"] == []


def test_title_from_text_truncates_long_description():
    long_desc = "伏" * 250
    title = _title_from_text(long_desc)
    assert len(title) <= 200
    assert title.endswith("…")
