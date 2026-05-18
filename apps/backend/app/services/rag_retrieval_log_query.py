"""管理端：跨项目查询 rag_retrieval_logs。"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.rag_retrieval_log import RagRetrievalLog


def list_rag_retrieval_logs(
    db: Session,
    *,
    limit: int = 200,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    project_id: Optional[UUID] = None,
    source: Optional[str] = None,
) -> List[RagRetrievalLog]:
    q = db.query(RagRetrievalLog)
    if since is not None:
        q = q.filter(RagRetrievalLog.created_at >= since)
    if until is not None:
        q = q.filter(RagRetrievalLog.created_at <= until)
    if project_id is not None:
        q = q.filter(RagRetrievalLog.project_id == project_id)
    if source:
        q = q.filter(RagRetrievalLog.source == source.strip())
    return (
        q.order_by(RagRetrievalLog.created_at.desc())
        .limit(max(1, min(limit, 2000)))
        .all()
    )
