"""Bootstrap 章纲 → Foreshadow 同步回归。"""

from __future__ import annotations

import uuid

from app.models import Foreshadow
from app.services.bootstrap.foreshadow_sync import (
    _RE_HEAT,
    _RE_LAY,
    _RE_RESOLVE,
    _title_from_text,
)


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


def test_foreshadow_op_regex_supports_common_brackets():
    """章纲五要素常见括号形态均应可解析。"""
    assert _RE_LAY.search("埋[神秘玉佩|主题:主角身世]").group(1) == "神秘玉佩|主题:主角身世"
    assert _RE_LAY.search("埋＜测试＞").group(1) == "测试"
    assert _RE_LAY.search("埋【青印线索】").group(1) == "青印线索"
    assert _RE_HEAT.search("加热[FM-01+主角追问]").group(1) == "FM-01+主角追问"
    assert _RE_RESOLVE.search("收[FM-01+真相揭晓]").group(1) == "FM-01+真相揭晓"


def test_title_from_text_truncates_long_description():
    long_desc = "伏" * 250
    title = _title_from_text(long_desc)
    assert len(title) <= 200
    assert title.endswith("…")


def test_keywords_overlap_avoids_short_false_positive():
    from app.services.bootstrap.foreshadow_sync import _keywords_overlap

    assert not _keywords_overlap("天生灵根的真相", "陆沉发现断路之战真相")
    assert _keywords_overlap("天生灵根的真相", "天生灵根并非天赋而是封印")
