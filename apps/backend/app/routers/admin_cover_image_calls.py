"""管理端：封面图片网关调用记录（cover_image_call_logs）。"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cover_image_call_log import CoverImageCallLog
from app.services.cover_image_call_query import list_cover_image_calls
from app.services.cover_log_preview import resolve_log_preview_image

router = APIRouter(prefix="/admin/cover-image-calls", tags=["admin-cover-image-calls"])


@router.get("/")
def list_cover_image_calls_route(
    limit: int = Query(default=200, ge=1, le=1000),
    since: Optional[datetime] = Query(default=None, description="含该时刻起（ISO8601）"),
    until: Optional[datetime] = Query(default=None, description="含该时刻止（ISO8601）"),
    project_id: Optional[UUID] = Query(default=None, description="按作品 ID 筛选"),
    db: Session = Depends(get_db),
):
    return list_cover_image_calls(
        db,
        limit=limit,
        since=since,
        until=until,
        project_id=project_id,
    )


@router.get("/{log_id}/preview")
def preview_cover_log_image(log_id: UUID, db: Session = Depends(get_db)):
    """
    返回该条记录可展示的图片：成功记录用落盘 WebP 或外链；
    失败记录优先 decoded_attempt.bin，其次尝试解码 payload.b64.txt。
    """
    row = db.query(CoverImageCallLog).filter(CoverImageCallLog.id == log_id).first()
    if not row:
        raise HTTPException(404, "记录不存在")
    try:
        data, media = resolve_log_preview_image(row)
    except FileNotFoundError:
        raise HTTPException(404, "暂无可预览图片")
    except Exception:
        raise HTTPException(502, "预览生成失败")
    return Response(content=data, media_type=media)
