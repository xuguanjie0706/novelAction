"""章节 ↔ 番茄草稿映射（存 Chapter.extra，下次同步走更新）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Chapter

_EXTRA_BOOK = "fanqie_book_id"
_EXTRA_ITEM = "fanqie_item_id"
_EXTRA_TITLE = "fanqie_title"
_EXTRA_SYNCED_AT = "fanqie_synced_at"
_EXTRA_VOLUME = "fanqie_volume_id"


def _chapter_extra(chapter: Chapter) -> dict[str, Any]:
    return dict(chapter.extra) if isinstance(chapter.extra, dict) else {}


def get_stored_fanqie_item_id(chapter: Chapter, book_id: str) -> str:
    """本章在该番茄书下已同步过的 item_id；无记录则返回空。"""
    extra = _chapter_extra(chapter)
    if str(extra.get(_EXTRA_BOOK) or "") != book_id:
        return ""
    return str(extra.get(_EXTRA_ITEM) or "")


def get_stored_fanqie_item_id_for_upload(
    db: Session,
    chapter: Chapter,
    project_id: UUID,
    book_id: str,
) -> str:
    """
    上传用 item_id：仅当本章独占该映射时返回；若多章共用一个 item_id（历史脏数据）则返回空以占新槽。
    """
    stored = get_stored_fanqie_item_id(chapter, book_id)
    if not stored:
        return ""
    rows = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id, Chapter.deleted_at.is_(None))
        .all()
    )
    owners = [r.id for r in rows if get_stored_fanqie_item_id(r, book_id) == stored]
    if len(owners) == 1 and owners[0] == chapter.id:
        return stored
    return ""


def get_fanqie_sync_meta(chapter: Chapter, book_id: str) -> dict[str, Any] | None:
    """读取同步元数据（供 API 返回 / 前端展示）。"""
    item_id = get_stored_fanqie_item_id(chapter, book_id)
    if not item_id:
        return None
    extra = _chapter_extra(chapter)
    return {
        "book_id": book_id,
        "item_id": item_id,
        "title": str(extra.get(_EXTRA_TITLE) or ""),
        "synced_at": str(extra.get(_EXTRA_SYNCED_AT) or ""),
        "volume_id": str(extra.get(_EXTRA_VOLUME) or ""),
    }


def resolve_chapter_title(chapter: Chapter, title_override: str | None = None) -> str:
    """番茄 cover_article 使用的章节标题。"""
    t = (title_override or "").strip() or (chapter.title or "").strip()
    if t:
        return t
    order = chapter.sort_order if chapter.sort_order is not None else 1
    return f"第{order}章"


def collect_book_fanqie_item_ids(
    db: Session,
    project_id: UUID,
    book_id: str,
    *,
    exclude_chapter_id: UUID | None = None,
) -> set[str]:
    """本书下已被其他章占用的番茄 item_id（批量同步时勿复用）。"""
    rows = (
        db.query(Chapter)
        .filter(
            Chapter.project_id == project_id,
            Chapter.deleted_at.is_(None),
        )
        .all()
    )
    used: set[str] = set()
    for row in rows:
        if exclude_chapter_id and row.id == exclude_chapter_id:
            continue
        iid = get_stored_fanqie_item_id(row, book_id)
        if iid:
            used.add(iid)
    return used


def persist_fanqie_sync(
    chapter: Chapter,
    *,
    book_id: str,
    item_id: str,
    title: str,
    volume_id: str = "",
    db: Session,
) -> None:
    """落库同步记录，后续同步同一 book_id 时强制带 item_id 更新。"""
    if not item_id:
        return
    extra = _chapter_extra(chapter)
    extra[_EXTRA_BOOK] = book_id
    extra[_EXTRA_ITEM] = item_id
    extra[_EXTRA_TITLE] = title
    extra[_EXTRA_SYNCED_AT] = datetime.now(timezone.utc).isoformat()
    if volume_id:
        extra[_EXTRA_VOLUME] = volume_id
    chapter.extra = extra
    db.commit()
