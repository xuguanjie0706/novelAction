"""
fanqie_proxy.py — 番茄小说 API 代理路由
========================================
职责：以后端身份转发请求到番茄小说作者 API，绕过浏览器 CORS 限制。
凭据（Cookie / Token）持久化到 FANQIE_CREDS_FILE（默认 apps/backend/fanqie_creds.json）。

端点：
  POST /api/v1/fanqie/config                        保存/更新凭据
  GET  /api/v1/fanqie/config                        读取凭据摘要（Cookie 脱敏显示）
  POST /api/v1/fanqie/upload-cover                    手动上传封面，返回 thumb_uri
  POST /api/v1/fanqie/projects/{project_id}/publish   创建书 + 批量上传草稿
  GET  /api/v1/fanqie/probe?path=...                调试：探测任意番茄 API 路径的原始响应
  GET  /api/v1/fanqie/books                         代理获取书籍列表
  GET  /api/v1/fanqie/books/{book_id}/chapters      代理获取章节/草稿列表
  GET  /api/v1/fanqie/user                          代理获取作者信息
"""
from __future__ import annotations

import json
import traceback
from typing import Any, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project
from app.services.fanqie.client import (
    BASE,
    COMMON_PARAMS,
    load_creds,
    make_client,
    prepare_creds_from_body,
    proxy_get,
    require_creds,
    save_creds,
)
from app.services.fanqie.normalize import merge_chapter_lists, normalize_books, normalize_chapters
from app.services.fanqie.cover import upload_cover_image
from app.services.fanqie.cover_image import fetch_cover_image
from app.services.fanqie.creds import creds_summary, merge_creds_from_curl
from app.services.fanqie.publish import publish_project_to_fanqie

router = APIRouter(prefix="/fanqie", tags=["fanqie"])

_PATH_BOOK_LIST = "/api/author/book/book_list/v0"
_PATH_CHAPTER_LIST = "/api/author/chapter/chapter_list/v1"
_PATH_DRAFT_LIST = "/api/author/chapter/draft_list/v1"


class FanqieConfig(BaseModel):
    """用户提交的番茄凭据。"""

    cookies: str
    csrf_token: str = ""
    ms_token: str = ""
    a_bogus: str = ""
    author_id: str = ""


class PublishProjectBody(BaseModel):
    """从 novelAction 项目发布到番茄。"""

    mode: Literal["create", "existing"] = "create"
    book_id: str = ""
    book_name: str = Field(default="", description="番茄书名，留空则用项目标题（最多 15 字）")
    category: str = Field(default="257,758,856,868", description="番茄分类 ID，逗号分隔")
    gender: int = Field(default=1, description="1=男频 2=女频")
    roles: list[str] | None = None
    thumb_uri: str = Field(default="", description="封面 URI，如 novel-pic-r/xxx（需在番茄上传过）")
    volume_id: str = ""
    volume_name: str = ""
    delay_seconds: float = Field(default=1.5, ge=0, le=10)
    chapter_ids: list[str] | None = None
    fresh_create_curl: str = Field(
        default="",
        description="DevTools 复制的 book/create cURL，用于刷新 msToken、a_bogus（有效期极短）",
    )
    upload_cover: bool = Field(default=True, description="创建新书时自动上传项目封面到番茄")
    content_html: str | None = Field(
        default=None,
        description="单章同步时可选：编辑器当前 HTML，优先于数据库 chapter.content",
    )
    chapter_title: str | None = Field(
        default=None,
        description="单章同步时可选：章节标题，优先于数据库 chapter.title",
    )


# ─────────────────────────────────────────
# 路由
# ─────────────────────────────────────────

@router.post("/config", summary="保存番茄凭据")
async def save_config(body: FanqieConfig):
    """
    保存番茄凭据（支持整段 cover_article cURL）。

    从 URL 自动提取并持久化 msToken、a_bogus；从 -b 提取 Cookie；从 --data-raw 提取默认卷信息。
    """
    creds = prepare_creds_from_body(
        body.cookies,
        csrf_token=body.csrf_token,
        ms_token=body.ms_token,
        a_bogus=body.a_bogus,
        author_id=body.author_id,
    )
    save_creds(creds)
    summary = creds_summary(creds)
    msg = "凭据已保存"
    if summary["has_ms_token"] and summary["has_a_bogus"]:
        msg = "凭据已保存（已提取 msToken、a_bogus，可上传草稿）"
    elif not summary["has_a_bogus"]:
        msg = "Cookie 已保存，但未检测到 a_bogus，请粘贴 cover_article 完整 cURL"
    return {"ok": True, "message": msg, **summary}


@router.get("/config", summary="读取凭据摘要")
async def get_config():
    """返回当前凭据摘要（Cookie 脱敏）。"""
    creds = load_creds()
    if not creds:
        return {"configured": False}

    cookie_str = creds.get("cookies", "")
    session_id = ""
    for part in cookie_str.split(";"):
        part = part.strip()
        if part.startswith("sessionid="):
            session_id = part.split("=", 1)[1][:8] + "…"
            break

    return {
        "session_preview": session_id,
        "author_id": creds.get("author_id", ""),
        **creds_summary(creds),
    }


@router.get("/cover-image", summary="代理拉取番茄书籍封面")
async def cover_image(
    url: str = Query("", description="thumb_url_list 中的签名 URL"),
    thumb_uri: str = Query("", description="novel-pic-r/xxx"),
):
    """
    用已保存的作家 Cookie 拉取封面，避免浏览器直连 CDN 403/空白。

    书单 normalize 后的 cover 字段即指向本接口。
    """
    body, content_type = await fetch_cover_image(url=url, thumb_uri=thumb_uri)
    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/upload-cover", summary="上传封面到番茄")
async def upload_cover(
    file: UploadFile = File(..., description="PNG/JPEG/WebP 封面"),
    book_id: str = Query("", description="可选，用于 referer"),
    fresh_curl: str = Query("", description="可选 upload_pic cURL，刷新 a_bogus"),
):
    """
    代理番茄 upload_pic_v1，返回 thumb_uri（如 novel-pic-r/xxx）。

    用于 book/create 的 thumb_uri 字段；创建前若 code=-2 参数有误，通常因缺有效封面。
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="空文件")

    creds = load_creds()
    if not creds.get("cookies"):
        raise HTTPException(status_code=403, detail="番茄凭据未配置")

    if fresh_curl.strip():
        creds = merge_creds_from_curl(creds, fresh_curl)
        save_creds(creds)

    mime = (file.content_type or "image/png").split(";")[0].strip()
    try:
        thumb_uri = await upload_cover_image(
            content,
            file.filename or "cover.png",
            mime,
            book_id=book_id,
            creds=creds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"thumb_uri": thumb_uri}


@router.post("/projects/{project_id}/publish", summary="发布项目到番茄")
async def publish_project(
    project_id: UUID,
    body: PublishProjectBody,
    db: Session = Depends(get_db),
):
    """
    将 novelAction 项目发布到番茄：可选先创建新书，再按 sort_order 上传章节草稿。

    凭据须先 POST /fanqie/config；创建书籍建议粘贴含 a_bogus 的 create cURL 以提取签名。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        result = await publish_project_to_fanqie(
            db,
            project,
            mode=body.mode,
            book_id=body.book_id,
            book_name=body.book_name,
            category=body.category,
            gender=body.gender,
            roles=body.roles,
            thumb_uri=body.thumb_uri,
            volume_id=body.volume_id,
            volume_name=body.volume_name,
            delay_seconds=body.delay_seconds,
            chapter_ids=body.chapter_ids,
            fresh_create_curl=body.fresh_create_curl,
            upload_cover=body.upload_cover,
            chapter_content_html=body.content_html,
            chapter_title=body.chapter_title,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result


@router.get("/probe", summary="调试：探测番茄 API 原始响应")
async def probe_endpoint(
    path: str = Query(..., description="要探测的番茄 API 路径，如 /api/author/book/book_list/v0"),
):
    """直接返回番茄 API 的原始 JSON，用于调试和确认正确端点。"""
    creds = require_creds()
    params = {**COMMON_PARAMS}
    ms_token = creds.get("ms_token", "").strip()
    if ms_token:
        params["msToken"] = ms_token
    bogus = creds.get("a_bogus", "").strip()
    if bogus:
        params["a_bogus"] = bogus

    try:
        async with make_client(creds) as client:
            resp = await client.get(path, params=params)
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            return {"status": resp.status_code, "body": resp.json()}
        return {"status": resp.status_code, "content_type": ct, "text_preview": resp.text[:500]}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-500:]}


@router.get("/user", summary="获取番茄作者信息")
async def get_user_info():
    """代理请求番茄作者状态接口（含实名认证状态）。"""
    data = await proxy_get("/api/author/verify/check_user_status/v0/")
    return {
        "author_id": load_creds().get("author_id", ""),
        "author_first_pass_status": data.get("author_first_pass_status") if isinstance(data, dict) else None,
        "raw": data,
    }


@router.get("/books", summary="获取书籍列表")
async def get_books(page_index: int = 0, page_count: int = 20):
    """代理请求番茄「我的书籍」列表（book-manage 页面同源 API）。"""
    data = await proxy_get(
        _PATH_BOOK_LIST,
        params={"page_index": page_index, "page_count": page_count},
    )
    return normalize_books(data)


@router.get("/books/{book_id}/chapters", summary="获取书籍章节/草稿列表")
async def get_chapters(
    book_id: str,
    page_index: int = 0,
    page_count: int = 50,
    status: str = Query("0", description='"0" 全部 / "1" 已发布 / "2" 草稿'),
):
    """
    代理请求番茄某书籍的章节列表。

    Args:
        book_id:  番茄书籍 ID。
        status:   "0" 全部（草稿 + 已发布），"1" 已发布，"2" 草稿。
    """
    referer = f"{BASE}/main/writer/chapter-manage/{book_id}"
    base_params = {
        "book_id": book_id,
        "page_index": page_index,
        "page_count": page_count,
    }

    if status == "2":
        data = await proxy_get(_PATH_DRAFT_LIST, params=base_params, referer=referer)
        return normalize_chapters(data, source="draft")

    if status == "1":
        data = await proxy_get(_PATH_CHAPTER_LIST, params=base_params, referer=referer)
        return normalize_chapters(data, source="published")

    draft_data = await proxy_get(_PATH_DRAFT_LIST, params=base_params, referer=referer)
    pub_data = await proxy_get(_PATH_CHAPTER_LIST, params=base_params, referer=referer)
    drafts = normalize_chapters(draft_data, source="draft")
    published = normalize_chapters(pub_data, source="published")
    return merge_chapter_lists(published, drafts)
