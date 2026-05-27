"""
番茄发布：创建书籍 + 批量上传章节草稿。

从 novelAction 项目数据映射到番茄作家后台 form 字段。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Chapter, Character, Project
from app.services.export_service import chapter_to_plain
from app.services.fanqie.client import BASE, load_creds, proxy_post, save_creds
from app.services.fanqie.cover import load_project_cover_bytes, upload_cover_image
from app.services.fanqie.creds import merge_creds_from_curl
from app.services.fanqie.html import plain_to_fanqie_html

_PATH_BOOK_CREATE = "/api/author/book/create/v0/"
_PATH_COVER_ARTICLE = "/api/author/article/cover_article/v0/"
_PATH_SAVE_HISTORY = "/api/author/article/save_doc_history/v0/"

_FANQIE_BOOK_NAME_MAX = 15
_FANQIE_ABSTRACT_MIN = 30


async def create_fanqie_book(
    *,
    book_name: str,
    abstract: str,
    category: str,
    gender: int,
    roles: list[str],
    thumb_uri: str = "",
    activity_id: int = 0,
    is_self_pic: int = 0,
    creds: dict | None = None,
) -> dict[str, Any]:
    """
    在番茄作家后台创建新书（对应 book/create/v0）。

    Returns:
        番茄 API data 字段，通常含 book_id。
    """
    referer = f"{BASE}/main/writer/create?enter_from=home"
    safe_name = (book_name or "未命名").strip()[:_FANQIE_BOOK_NAME_MAX]
    safe_abstract = (abstract or safe_name).strip()
    if len(safe_abstract) < _FANQIE_ABSTRACT_MIN:
        pad = "。" * (_FANQIE_ABSTRACT_MIN - len(safe_abstract) + 1)
        safe_abstract = (safe_abstract + pad)[:500]

    form = {
        "aid": "2503",
        "app_name": "muye_novel",
        "book_name": safe_name,
        "roles": json.dumps(roles[:5], ensure_ascii=False),
        "category": category,
        "gender": str(gender),
        "thumb_uri": thumb_uri,
        "abstract": safe_abstract,
        "activity_id": str(activity_id),
        "is_self_pic": str(is_self_pic),
    }
    return await proxy_post(_PATH_BOOK_CREATE, form, referer=referer, creds=creds)


async def upload_fanqie_draft(
    *,
    book_id: str,
    title: str,
    content_html: str,
    volume_id: str = "",
    volume_name: str = "",
) -> dict[str, Any]:
    """新建一章草稿（cover_article，不传 item_id）。"""
    referer = f"{BASE}/main/writer/{book_id}/"
    form = {
        "aid": "2503",
        "app_name": "muye_novel",
        "book_id": book_id,
        "title": title,
        "content": content_html,
        "volume_name": volume_name,
        "volume_id": volume_id,
    }
    return await proxy_post(_PATH_COVER_ARTICLE, form, referer=referer)


async def save_fanqie_doc_history(*, book_id: str, item_id: str) -> None:
    """与番茄前端一致：保存草稿历史版本（失败不阻断主流程）。"""
    referer = f"{BASE}/main/writer/{book_id}/"
    form = {
        "aid": "2503",
        "app_name": "muye_novel",
        "book_id": book_id,
        "item_id": item_id,
    }
    try:
        await proxy_post(_PATH_SAVE_HISTORY, form, referer=referer)
    except Exception:
        pass


def _default_roles(db: Session, project_id: str) -> list[str]:
    chars = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.created_at.asc())
        .limit(5)
        .all()
    )
    names = [c.name.strip() for c in chars if c.name and c.name.strip()]
    return names[:2] if names else ["主角", "配角"]


def _extract_book_id(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("book_id", "bookId", "id"):
        val = data.get(key)
        if val:
            return str(val)
    book = data.get("book")
    if isinstance(book, dict):
        for key in ("book_id", "bookId", "id"):
            val = book.get(key)
            if val:
                return str(val)
    return ""


def _extract_item_id(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("item_id", "itemId", "articleId", "id"):
        val = data.get(key)
        if val:
            return str(val)
    return ""


async def publish_project_to_fanqie(
    db: Session,
    project: Project,
    *,
    mode: str,
    book_id: str = "",
    book_name: str = "",
    category: str,
    gender: int,
    roles: list[str] | None,
    thumb_uri: str,
    volume_id: str,
    volume_name: str,
    delay_seconds: float,
    chapter_ids: list[str] | None,
    fresh_create_curl: str = "",
    upload_cover: bool = False,
) -> dict[str, Any]:
    """
    将项目章节批量上传到番茄草稿箱。

    mode:
      - ``create``: 先 create_fanqie_book，再上传章节
      - ``existing``: 使用已有 book_id 仅上传章节
    """
    creds = load_creds()
    if not creds.get("cookies"):
        raise ValueError("番茄凭据未配置，请先在「我的番茄」或本页连接账号")

    if fresh_create_curl.strip():
        creds = merge_creds_from_curl(creds, fresh_create_curl)
        save_creds(creds)

    resolved_roles = roles if roles else _default_roles(db, str(project.id))

    created = False
    target_book_id = book_id.strip()
    resolved_thumb = thumb_uri.strip()
    cover_uploaded = False

    if mode == "create":
        if not resolved_thumb and upload_cover:
            try:
                raw, ct, name = await load_project_cover_bytes(project)
                resolved_thumb = await upload_cover_image(raw, name, ct, creds=creds)
                cover_uploaded = True
            except ValueError:
                pass

        if not resolved_thumb:
            raise ValueError(
                "创建新书需要封面 thumb_uri：请在本页「上传封面到番茄」选择图片，"
                "或手动填写 thumb_uri，或为项目设置封面并勾选自动上传"
            )

        if not creds.get("a_bogus", "").strip():
            raise ValueError(
                "创建书籍需要有效的 a_bogus 签名：请在下方粘贴 DevTools 复制的 book/create cURL（含 msToken、a_bogus）"
            )

        resolved_name = (book_name or project.title or "未命名").strip()
        abstract = (project.premise or project.logline or project.title or "")[:2000]
        create_data = await create_fanqie_book(
            book_name=resolved_name,
            abstract=abstract,
            category=category,
            gender=gender,
            roles=resolved_roles,
            thumb_uri=resolved_thumb,
            is_self_pic=1,
            creds=creds,
        )
        target_book_id = _extract_book_id(create_data)
        if not target_book_id:
            raise ValueError("番茄创建书籍成功但未返回 book_id，请检查账号或 a_bogus 是否过期")
        created = True
        extra = dict(project.extra or {})
        extra["fanqie_book_id"] = target_book_id
        project.extra = extra
        db.commit()
    elif not target_book_id:
        raise ValueError("existing 模式必须提供 book_id")

    q = db.query(Chapter).filter(
        Chapter.project_id == project.id,
        Chapter.deleted_at.is_(None),
    )
    if chapter_ids:
        q = q.filter(Chapter.id.in_(chapter_ids))
    chapters = q.order_by(Chapter.sort_order.asc()).all()
    chapters = [c for c in chapters if (c.word_count or 0) > 0 or (c.content or "").strip()]

    uploaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for ch in chapters:
        plain = chapter_to_plain(ch)
        if not plain.strip():
            continue
        title = ch.title or f"第{ch.sort_order}章"
        html = plain_to_fanqie_html(plain)
        try:
            data = await upload_fanqie_draft(
                book_id=target_book_id,
                title=title,
                content_html=html,
                volume_id=volume_id,
                volume_name=volume_name,
            )
            item_id = _extract_item_id(data)
            if item_id:
                await save_fanqie_doc_history(book_id=target_book_id, item_id=item_id)
            uploaded.append({
                "chapter_id": str(ch.id),
                "title": title,
                "item_id": item_id,
                "status": "ok",
            })
        except Exception as exc:
            failed.append({
                "chapter_id": str(ch.id),
                "title": title,
                "status": "error",
                "message": str(exc),
            })
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    return {
        "book_id": target_book_id,
        "created": created,
        "cover_uploaded": cover_uploaded,
        "thumb_uri": resolved_thumb or None,
        "uploaded": uploaded,
        "failed": failed,
        "total_chapters": len(uploaded) + len(failed),
    }
