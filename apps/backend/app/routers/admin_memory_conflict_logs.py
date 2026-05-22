"""管理端：记忆冲突检测运行日志（memory_conflict_detect_logs）。"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.memory import MemoryConflictDetectLogOut
from app.services.memory_conflict_detect_log import list_memory_conflict_detect_logs

router = APIRouter(prefix="/admin/memory-conflict-logs", tags=["admin-memory-conflict-logs"])


@router.get("/", response_model=List[MemoryConflictDetectLogOut])
def list_memory_conflict_logs_route(
    limit: int = Query(default=200, ge=1, le=1000),
    since: Optional[datetime] = Query(default=None, description="含该时刻起（ISO8601）"),
    until: Optional[datetime] = Query(default=None, description="含该时刻止（ISO8601）"),
    project_id: Optional[UUID] = Query(default=None, description="按作品 ID 筛选"),
    trigger: Optional[str] = Query(default=None, description="manual | chapter_debrief"),
    status: Optional[str] = Query(default=None, description="ok | error | skipped"),
    db: Session = Depends(get_db),
):
    """跨项目列出记忆冲突检测运行日志。"""
    return list_memory_conflict_detect_logs(
        db,
        limit=limit,
        since=since,
        until=until,
        project_id=project_id,
        trigger=trigger,
        status=status,
    )
