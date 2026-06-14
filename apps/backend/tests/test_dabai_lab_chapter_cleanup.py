"""dabai 清章写作产物单元测试。"""
from unittest.mock import MagicMock

from app.services.dabai.lab_chapter_cleanup import (
    clear_dabai_chapter_writing,
    later_chapters_have_content,
)


def test_later_chapters_have_content():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = object()
    assert later_chapters_have_content(db, "pid", 2) is True

    db.query.return_value.filter.return_value.first.return_value = None
    assert later_chapters_have_content(db, "pid", 2) is False


def test_clear_raises_when_later_written(monkeypatch):
    db = MagicMock()
    project = MagicMock(id="pid")
    ch = MagicMock(id="cid", chapter_number=2, content="正文", project_id="pid")

    monkeypatch.setattr(
        "app.services.dabai.lab_chapter_cleanup.later_chapters_have_content",
        lambda *_a, **_k: True,
    )

    try:
        clear_dabai_chapter_writing(db, project, ch)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "后续章节" in str(exc)
