"""番茄 API 原始响应 → 前端统一结构。"""
from __future__ import annotations

from typing import Any

from app.services.fanqie.cover_image import cover_proxy_path


def _int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _pick_cover_url(item: dict[str, Any]) -> str | None:
    """
    从书籍条目提取创作端可展示的封面路径（经同源代理，带作家 Cookie）。

    番茄 book_list 常返回 thumb_url_list（带签名外链）；浏览器直连易 403/空白，
    统一走 /api/v1/fanqie/cover-image 代理。
    """
    thumb_uri = (item.get("thumb_uri") or item.get("pic_uri") or "").strip()

    thumb_list = item.get("thumb_url_list")
    if isinstance(thumb_list, list):
        for entry in thumb_list:
            if isinstance(entry, str) and entry.strip().startswith("http"):
                return cover_proxy_path(url=entry.strip())
            if not isinstance(entry, dict):
                continue
            for key in ("main_url", "backup_url", "url"):
                url = (entry.get(key) or "").strip()
                if url.startswith("http"):
                    return cover_proxy_path(url=url)

    for key in ("cover", "thumb_url", "cover_url", "book_pic", "horizontal_thumb_url"):
        url = item.get(key)
        if isinstance(url, str) and url.strip().startswith("http"):
            return cover_proxy_path(url=url.strip())

    if thumb_uri.startswith("http"):
        return cover_proxy_path(url=thumb_uri)

    if thumb_uri:
        return cover_proxy_path(thumb_uri=thumb_uri)

    return None


def normalize_books(data: Any) -> dict[str, Any]:
    """将 book_list/v0 响应转为 { books, total }。"""
    if isinstance(data, list):
        raw_list = data
        total = len(data)
    elif isinstance(data, dict):
        raw_list = data.get("book_list") or data.get("list") or []
        total = _int(data.get("total_count") or data.get("total") or len(raw_list))
    else:
        raw_list, total = [], 0

    books = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        books.append({
            "book_id": str(item.get("book_id") or ""),
            "book_name": item.get("book_name") or item.get("name") or "未命名",
            "cover": _pick_cover_url(item),
            "abstract": item.get("abstract") or item.get("desc") or "",
            "word_count": _int(item.get("word_count")),
            "chapter_count": _int(item.get("chapter_number") or item.get("chapter_count")),
            "status": _int(item.get("creation_status", item.get("status"))),
            "create_time": _int(item.get("create_time")),
            "update_time": _int(item.get("last_chapter_time") or item.get("update_time")),
            "last_chapter_title": item.get("last_chapter_title") or "",
        })

    return {"books": books, "total": total}


def _normalize_chapter_item(item: dict[str, Any], *, is_published: bool) -> dict[str, Any]:
    article_status = _int(item.get("article_status") or item.get("status"))
    return {
        "item_id": str(item.get("item_id") or ""),
        "title": item.get("title") or "（无标题）",
        "word_count": _int(item.get("word_number") or item.get("word_count")),
        "create_time": _int(item.get("create_time") or item.get("modify_time")),
        "update_time": _int(item.get("modify_time") or item.get("create_time")),
        "is_published": is_published,
        "status": article_status,
        "volume_id": str(item.get("volume_id") or ""),
        "index": _int(item.get("index"), default=-1),
    }


def normalize_chapters(data: Any, *, source: str = "published") -> dict[str, Any]:
    """
    将 chapter_list/v1 或 draft_list/v1 响应转为 { chapters, total }。

    Args:
        source: "published" | "draft" | "all"
    """
    if not isinstance(data, dict):
        return {"chapters": [], "total": 0}

    if source == "draft":
        raw_list = data.get("draft_list") or []
        total = _int(data.get("total_count") or len(raw_list))
        chapters = [_normalize_chapter_item(it, is_published=False) for it in raw_list if isinstance(it, dict)]
        return {"chapters": chapters, "total": total}

    raw_list = data.get("item_list") or data.get("article_list") or data.get("list") or []
    total = _int(data.get("total_count") or len(raw_list))
    chapters = [_normalize_chapter_item(it, is_published=True) for it in raw_list if isinstance(it, dict)]
    return {"chapters": chapters, "total": total}


def merge_chapter_lists(published: dict[str, Any], drafts: dict[str, Any]) -> dict[str, Any]:
    """合并已发布章节与草稿，草稿排在前面（按 modify_time 降序）。"""
    draft_items = sorted(
        drafts.get("chapters", []),
        key=lambda c: c.get("update_time", 0),
        reverse=True,
    )
    pub_items = published.get("chapters", [])
    merged = draft_items + pub_items
    return {
        "chapters": merged,
        "total": _int(published.get("total")) + _int(drafts.get("total")),
        "draft_count": len(draft_items),
        "published_count": len(pub_items),
    }
