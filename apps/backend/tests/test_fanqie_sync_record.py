"""番茄章节同步记录。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.fanqie.sync_record import (
    get_stored_fanqie_item_id,
    persist_fanqie_sync,
    resolve_chapter_title,
)


def test_resolve_chapter_title_prefers_override():
    ch = SimpleNamespace(title="旧标题", sort_order=1)
    assert resolve_chapter_title(ch, "新标题") == "新标题"


def test_get_stored_item_id_requires_matching_book():
    ch = SimpleNamespace(
        extra={"fanqie_book_id": "111", "fanqie_item_id": "222"},
    )
    assert get_stored_fanqie_item_id(ch, "111") == "222"
    assert get_stored_fanqie_item_id(ch, "999") == ""


def test_persist_fanqie_sync_writes_extra():
    ch = SimpleNamespace(extra={})
    db = MagicMock()
    persist_fanqie_sync(
        ch,
        book_id="111",
        item_id="222",
        title="第1章：测试",
        volume_id="vol1",
        db=db,
    )
    assert ch.extra["fanqie_item_id"] == "222"
    assert ch.extra["fanqie_title"] == "第1章：测试"
    assert ch.extra["fanqie_synced_at"]
    db.commit.assert_called_once()
