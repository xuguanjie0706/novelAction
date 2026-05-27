"""卷级结构化战力时间轴（只读聚合 + 可选持久化快照）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project
from app.routers.outline.helpers.power_timeline import build_power_timeline
from app.routers.outline.schemas import PowerTimelineOut

router = APIRouter()


@router.get("/power-timeline", response_model=PowerTimelineOut)
def get_power_timeline(
    project_id: str,
    persist: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """返回卷级结构化战力时间轴；persist=true 时写入 Project.extra 快照。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    try:
        pid = uuid.UUID(project_id)
    except ValueError as exc:
        raise HTTPException(400, "Invalid project_id") from exc
    payload = build_power_timeline(db, pid, persist=persist)
    return PowerTimelineOut(**payload)
