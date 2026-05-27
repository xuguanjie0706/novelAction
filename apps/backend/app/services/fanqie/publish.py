"""
番茄发布：创建书籍 + 批量上传章节草稿。

作家后台保存草稿的两步（与 DevTools 一致）：

1. **cover_article/v0** — 写入标题 + 正文 HTML（新建不传 item_id；更新传 item_id）
2. **save_doc_history/v0** — 落历史版本（仅 book_id + item_id，无正文）

用户粘贴的 save_doc_history cURL 可用于刷新 msToken/a_bogus/csrf，但上传正文须走 cover_article。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Chapter, Character, Project
from app.services.export_service import chapter_to_plain
from app.services.fanqie.client import BASE, load_creds, proxy_post, save_creds
from app.services.fanqie.html import chapter_html_to_fanqie_html, fanqie_html_plain_length
from app.services.fanqie.cover import load_project_cover_bytes, upload_cover_image
from app.services.fanqie.creds import ensure_fanqie_post_creds, merge_creds_from_curl
from app.services.fanqie.draft_resolve import (
    fanqie_error_hint,
    fetch_book_volume,
    resolve_fanqie_item_id,
)
from app.services.fanqie.new_article import create_fanqie_new_article
from app.services.fanqie.sync_record import (
    collect_book_fanqie_item_ids,
    get_stored_fanqie_item_id_for_upload,
    persist_fanqie_sync,
    resolve_chapter_title,
)

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


def _draft_editor_referer(
    book_id: str,
    item_id: str = "",
    *,
    enter_from: str = "newdraft",
) -> str:
    """与作家后台编辑页 Referer 对齐（更新=newdraft，新建章节=newchapter_0）。"""
    if item_id:
        return f"{BASE}/main/writer/{book_id}/publish/{item_id}?enter_from={enter_from}"
    return f"{BASE}/main/writer/{book_id}/"


async def upload_fanqie_draft(
    *,
    book_id: str,
    title: str,
    content_html: str,
    item_id: str = "",
    volume_id: str = "",
    volume_name: str = "",
    enter_from: str = "newdraft",
) -> dict[str, Any]:
    """
    保存草稿正文（cover_article/v0）。

    须先通过 new_article 或已有映射获得 item_id；新建章节用 enter_from=newchapter_0。
    """
    referer = _draft_editor_referer(book_id, item_id, enter_from=enter_from)
    form: dict[str, str] = {
        "aid": "2503",
        "app_name": "muye_novel",
        "book_id": book_id,
        "title": title,
        "content": content_html,
        "volume_name": volume_name,
        "volume_id": volume_id,
    }
    if item_id:
        form["item_id"] = item_id
    return await proxy_post(_PATH_COVER_ARTICLE, form, referer=referer)


async def save_fanqie_doc_history(*, book_id: str, item_id: str) -> None:
    """第 2 步：保存草稿历史版本（失败不阻断主流程）。"""
    referer = _draft_editor_referer(book_id, item_id)
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


def _chapter_fanqie_html(chapter: Chapter, content_override: str | None = None) -> str:
    """优先使用请求携带的编辑器 HTML，否则读 DB 经清洗后转番茄 HTML。"""
    if content_override is not None and content_override.strip():
        return chapter_html_to_fanqie_html(content_override)
    raw = (chapter.content or "").strip()
    if raw:
        return chapter_html_to_fanqie_html(raw)
    plain = chapter_to_plain(chapter)
    return chapter_html_to_fanqie_html(plain) if plain.strip() else ""


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
    chapter_content_html: str | None = None,
    chapter_title: str | None = None,
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

    # 上传草稿 / 创建书籍均为 POST，缺 msToken、a_bogus 时番茄返回空 text/plain
    ensure_fanqie_post_creds(creds)

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

    book_volume_id, book_volume_name = await fetch_book_volume(target_book_id)
    if not volume_id.strip():
        volume_id = book_volume_id
    if not volume_name.strip():
        volume_name = book_volume_name
    # 仅当凭据 cURL 来自同一本书时才用 default_volume（避免 A 书卷 ID 写到 B 书）
    if creds.get("default_book_id") == target_book_id:
        if not volume_id.strip() and creds.get("default_volume_id"):
            volume_id = str(creds.get("default_volume_id") or "")
        if not volume_name.strip() and creds.get("default_volume_name"):
            volume_name = str(creds.get("default_volume_name") or "")
    if not volume_id.strip():
        raise ValueError(
            f"无法解析书籍 {target_book_id} 的卷 volume_id，"
            "请先在番茄作家后台打开该书并保存一次草稿后再同步"
        )

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
    skipped_empty = 0

    single_chapter = chapter_ids is not None and len(chapter_ids) == 1
    content_override = chapter_content_html if single_chapter else None
    title_override = chapter_title.strip() if single_chapter and chapter_title else None

    # 本书已被各章占用的草稿 id；同批上传时动态追加，避免多章写入同一条
    occupied_item_ids = collect_book_fanqie_item_ids(db, project.id, target_book_id)

    for ch in chapters:
        html = _chapter_fanqie_html(
            ch,
            content_override if single_chapter and str(ch.id) == (chapter_ids[0] if chapter_ids else "") else None,
        )
        plain_len = fanqie_html_plain_length(html)
        if plain_len < 10:
            skipped_empty += 1
            failed.append({
                "chapter_id": str(ch.id),
                "title": ch.title or "",
                "status": "error",
                "message": "正文为空或过短：请先在编辑器保存章节后再同步，或确认章节已有内容",
            })
            continue
        title = resolve_chapter_title(
            ch,
            title_override if single_chapter and str(ch.id) == (chapter_ids[0] if chapter_ids else "") else None,
        )
        stored_item_id = get_stored_fanqie_item_id_for_upload(
            db, ch, project.id, target_book_id,
        )
        sync_mode = "update" if stored_item_id else "create"
        exclude_ids = {x for x in occupied_item_ids if x != stored_item_id}
        item_id, slot_hint = await resolve_fanqie_item_id(
            target_book_id,
            title,
            stored_item_id,
            allow_unnamed_slot=False,
            exclude_item_ids=exclude_ids,
        )
        enter_from = "newdraft"
        if not item_id and not stored_item_id:
            try:
                item_id = await create_fanqie_new_article(
                    book_id=target_book_id,
                    volume_id=volume_id,
                    volume_name=volume_name,
                )
                slot_hint = "已通过番茄 new_article 新建章节"
                enter_from = "newchapter_0"
            except Exception as exc:
                failed.append({
                    "chapter_id": str(ch.id),
                    "title": title,
                    "status": "error",
                    "message": f"新建番茄章节失败: {exc}",
                })
                continue

        try:
            data = await upload_fanqie_draft(
                book_id=target_book_id,
                title=title,
                content_html=html,
                item_id=item_id,
                volume_id=volume_id,
                volume_name=volume_name,
                enter_from=enter_from,
            )
            new_item_id = _extract_item_id(data) or item_id
            if not new_item_id and not stored_item_id:
                raise ValueError(
                    "未能获得番茄草稿 item_id：请先在作家后台新建空白草稿后再同步本章"
                )
            if new_item_id:
                await save_fanqie_doc_history(book_id=target_book_id, item_id=new_item_id)
                persist_fanqie_sync(
                    ch,
                    book_id=target_book_id,
                    item_id=new_item_id,
                    title=title,
                    volume_id=volume_id,
                    db=db,
                )
                occupied_item_ids.add(new_item_id)
            uploaded.append({
                "chapter_id": str(ch.id),
                "title": title,
                "item_id": new_item_id,
                "status": "ok",
                "sync_mode": sync_mode,
                "content_chars": plain_len,
                "message": slot_hint or None,
            })
        except Exception as exc:
            raw = str(exc)
            if "code=-2004" in raw or "章节不存在" in raw:
                raw = fanqie_error_hint(-2004, "章节不存在")
            failed.append({
                "chapter_id": str(ch.id),
                "title": title,
                "status": "error",
                "message": raw,
            })
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    if not uploaded and not failed and (skipped_empty > 0 or not chapters):
        raise ValueError(
            "没有可上传的正文：请确认章节已保存且含有内容，"
            "或检查 chapter_ids 是否属于当前项目"
        )

    return {
        "book_id": target_book_id,
        "created": created,
        "cover_uploaded": cover_uploaded,
        "thumb_uri": resolved_thumb or None,
        "uploaded": uploaded,
        "failed": failed,
        "skipped_empty": skipped_empty,
        "total_chapters": len(uploaded) + len(failed),
    }
