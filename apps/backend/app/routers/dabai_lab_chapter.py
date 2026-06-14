"""dabai 实验书架 — 章节写作产物管理（清空正文与派生数据）。"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.dabai import DabaiChapterOutline
from app.models.user import User
from app.routers.dabai import _owned_or_404
from app.routers.dabai_lab_ai import _chapter_or_404
from app.services.dabai.lab_chapter_cleanup import clear_dabai_chapter_writing

router = APIRouter(prefix="/dabai", tags=["dabai-lab-chapter"])


@router.delete("/projects/{project_id}/chapters/{chapter_id}/writing")
def delete_chapter_writing(
    project_id: UUID,
    chapter_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """清空本章正文及写作期全部派生数据（预警/分场/质检/记忆/复盘台账变更）。

    章纲五拍保留，便于按章纲重新生成。若后续章已有正文则拒绝（须从高章号先清）。
    """
    project = _owned_or_404(db, project_id, user)
    ch = _chapter_or_404(db, project, chapter_id)
    try:
        result = clear_dabai_chapter_writing(db, project, ch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "ok": True,
        "chapter_id": result.chapter_id,
        "chapter_number": result.chapter_number,
        "status": ch.status,
        "cleared": result.counts,
    }
