"""管理端：dabai 实验书架章节质检历史（dabai_quality_reports）。"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.dabai.lab_quality_query import (
    get_dabai_quality_report,
    list_dabai_quality_reports,
)

router = APIRouter(prefix="/admin/dabai-quality-logs", tags=["admin-dabai-quality-logs"])


class DabaiQualityLogOut(BaseModel):
    id: str
    project_id: str
    chapter_id: str
    chapter_number: Optional[int] = None
    source: str = "manual"
    status: Optional[str] = None
    overall_score: Optional[int] = None
    content_word_count: Optional[int] = None
    content_head_preview: str = ""
    continuity_score: Optional[int] = None
    continuity_issue: str = ""
    opening_continues_prev_tail: Optional[bool] = None
    location_bridge_needed: Optional[bool] = None
    prev_outline_location: Optional[str] = None
    curr_outline_location: Optional[str] = None
    created_at: str = ""


@router.get("/", response_model=List[DabaiQualityLogOut])
def list_dabai_quality_logs(
    limit: int = Query(default=200, ge=1, le=1000),
    since: Optional[datetime] = Query(default=None),
    until: Optional[datetime] = Query(default=None),
    project_id: Optional[UUID] = Query(default=None),
    chapter_id: Optional[UUID] = Query(default=None),
    chapter_number: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    """跨项目列出 dabai 质检历史（每次质检一条，可回归对比）。"""
    return list_dabai_quality_reports(
        db,
        limit=limit,
        since=since,
        until=until,
        project_id=project_id,
        chapter_id=chapter_id,
        chapter_number=chapter_number,
        include_report=False,
    )


@router.get("/{report_id}")
def get_dabai_quality_log_detail(
    report_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    """单条质检详情（含完整 report JSON 与 continuity_snapshot）。"""
    row = get_dabai_quality_report(db, report_id)
    if not row:
        raise HTTPException(status_code=404, detail="质检记录不存在")
    return row
