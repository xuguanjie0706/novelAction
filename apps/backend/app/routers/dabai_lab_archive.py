"""dabai 实验书架「情节档案」端点 — 按章聚合的回看视图（纯读）。

资源边界：仅读 dabai_* 表，复用 lab_chapter_archive 聚合服务。前缀 /dabai。
单独成文件避免 dabai_lab_ai.py 继续膨胀（见代码结构红线）。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.dabai import DabaiChapterOutline
from app.models.user import User
from app.routers.dabai import _owned_or_404
from app.services.dabai.lab_chapter_archive import (
    build_chapter_archive, build_project_archive,
)

router = APIRouter(prefix="/dabai", tags=["dabai-lab-archive"])


@router.get("/projects/{project_id}/archive")
def lab_project_archive(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """全书每章情节档案（章号升序）：计划五拍 + 复盘实际 + 线索/资产/关系变更。"""
    project = _owned_or_404(db, project_id, user)
    items = build_project_archive(db, project)
    return {"items": items, "total": len(items)}


@router.get("/projects/{project_id}/chapters/{chapter_id}/archive")
def lab_chapter_archive(
    project_id: UUID,
    chapter_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """单章情节档案（右侧栏随章卡数据源）。"""
    project = _owned_or_404(db, project_id, user)
    ch = (
        db.query(DabaiChapterOutline)
        .filter(DabaiChapterOutline.id == chapter_id,
                DabaiChapterOutline.project_id == project.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="章节不存在")
    return build_chapter_archive(db, project, ch)
