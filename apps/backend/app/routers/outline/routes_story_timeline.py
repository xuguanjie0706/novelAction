"""全书故事时间线横轴甘特（只读聚合）。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project

from app.routers.outline.helpers.story_timeline import build_story_timeline
from app.routers.outline.schemas import StoryTimelineOut

router = APIRouter()


@router.get("/story-timeline", response_model=StoryTimelineOut)
def get_story_timeline(project_id: str, db: Session = Depends(get_db)):
    """
    全局时间线：以章序为横轴，聚合卷/章节/故事线/势力/伏笔/承诺/境界条带。

    供创作端 GlobalTimelinePage 渲染甘特泳道；数据来自现有表字段，无新表。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    try:
        pid = uuid.UUID(project_id)
    except ValueError as exc:
        raise HTTPException(400, "Invalid project_id") from exc
    payload = build_story_timeline(db, pid)
    return StoryTimelineOut(**payload)
