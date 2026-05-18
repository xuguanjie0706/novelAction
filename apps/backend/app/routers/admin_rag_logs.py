"""管理端：RAG 记忆检索日志（rag_retrieval_logs）。"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.rag import RagRetrievalLogOut
from app.services.rag_retrieval_log_query import list_rag_retrieval_logs

router = APIRouter(prefix="/admin/rag-logs", tags=["admin-rag-logs"])


@router.get("/", response_model=List[RagRetrievalLogOut])
def list_rag_logs_route(
    limit: int = Query(default=200, ge=1, le=1000),
    since: Optional[datetime] = Query(default=None, description="含该时刻起（ISO8601）"),
    until: Optional[datetime] = Query(default=None, description="含该时刻止（ISO8601）"),
    project_id: Optional[UUID] = Query(default=None, description="按作品 ID 筛选"),
    source: Optional[str] = Query(
        default=None,
        description="draft_context | pre_write_warning | suggest | rag_query",
    ),
    db: Session = Depends(get_db),
):
    """跨项目列出 RAG 检索日志（写章 / 写前预警 / 建议 / 手动查询）。"""
    return list_rag_retrieval_logs(
        db,
        limit=limit,
        since=since,
        until=until,
        project_id=project_id,
        source=source,
    )
