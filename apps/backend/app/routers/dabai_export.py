"""dabai 实验书架 — 导出 & 投稿包路由。

GET /api/v1/dabai/projects/{project_id}/export/preview   字数合规预检
GET /api/v1/dabai/projects/{project_id}/export/txt       下载 TXT 全文
GET /api/v1/dabai/projects/{project_id}/export/outline   下载章纲大纲 TXT
GET /api/v1/dabai/projects/{project_id}/export/package   下载 ZIP 投稿包
"""
from __future__ import annotations

import urllib.parse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.user import User
from app.routers.dabai import _owned_or_404
from app.services.dabai.lab_export import (
    build_dabai_outline_txt,
    build_dabai_txt,
    build_dabai_zip,
    chapters_with_content,
    check_dabai_compliance,
)
from app.services.export_service import PLATFORM_RULES

router = APIRouter(prefix="/dabai", tags=["dabai"])


def _safe_filename(name: str) -> str:
    encoded = urllib.parse.quote(name, safe="")
    return f"filename*=UTF-8''{encoded}"


def _load_chapters(db: Session, project: DabaiProject) -> list[DabaiChapterOutline]:
    return (
        db.query(DabaiChapterOutline)
        .filter(DabaiChapterOutline.project_id == project.id)
        .order_by(DabaiChapterOutline.chapter_number.asc())
        .all()
    )


class ChapterIssueOut(BaseModel):
    chapter_id: str
    title: str
    sort_order: int
    word_count: int
    status: str
    message: str


class ExportPreviewOut(BaseModel):
    total_chapters: int
    total_words: int
    platform: str
    platform_name: str
    compliant_chapters: int
    issues: list[ChapterIssueOut]
    platforms: dict


@router.get("/projects/{project_id}/export/preview", response_model=ExportPreviewOut)
def dabai_export_preview(
    project_id: UUID,
    platform: str = Query("general"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """导出合规预检（纯 DB，毫秒响应）。"""
    project = _owned_or_404(db, project_id, user)
    chapters = _load_chapters(db, project)
    if platform not in PLATFORM_RULES:
        platform = "general"
    preview = check_dabai_compliance(chapters, platform)
    return ExportPreviewOut(
        total_chapters=preview.total_chapters,
        total_words=preview.total_words,
        platform=preview.platform,
        platform_name=preview.platform_name,
        compliant_chapters=preview.compliant_chapters,
        issues=[ChapterIssueOut(**vars(i)) for i in preview.issues],
        platforms={
            k: {"name": v["name"], "min_words": v["min_words"], "max_words": v["max_words"]}
            for k, v in PLATFORM_RULES.items()
        },
    )


@router.get("/projects/{project_id}/export/txt")
def dabai_export_txt(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """下载全书 TXT 纯文本（跳过空章）。"""
    project = _owned_or_404(db, project_id, user)
    chapters = chapters_with_content(_load_chapters(db, project))
    if not chapters:
        raise HTTPException(400, "暂无已完成章节，无法导出")
    txt = build_dabai_txt(project, chapters)
    safe_name = _safe_filename(f"{project.title or 'novel'}.txt")
    return Response(
        content=txt.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; {safe_name}"},
    )


@router.get("/projects/{project_id}/export/outline")
def dabai_export_outline(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """下载章纲大纲 TXT（卷 → 章 + 五拍）。"""
    project = _owned_or_404(db, project_id, user)
    chapters = _load_chapters(db, project)
    if not chapters:
        raise HTTPException(400, "暂无章纲内容，无法导出")
    txt = build_dabai_outline_txt(project, list(project.volumes), chapters)
    safe_name = _safe_filename(f"{project.title or 'novel'}_章纲.txt")
    return Response(
        content=txt.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; {safe_name}"},
    )


@router.get("/projects/{project_id}/export/package")
def dabai_export_package(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """下载 ZIP 投稿包（全文 + 分章 + manifest）。"""
    project = _owned_or_404(db, project_id, user)
    chapters = chapters_with_content(_load_chapters(db, project))
    if not chapters:
        raise HTTPException(400, "暂无已完成章节，无法打包")
    zip_bytes = build_dabai_zip(project, chapters)
    safe_name = _safe_filename(f"{project.title or 'novel'}_投稿包.zip")
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; {safe_name}"},
    )
