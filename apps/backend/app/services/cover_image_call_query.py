"""管理端查询 cover_image_call_logs。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.cover_image_call_log import CoverImageCallLog


def _row_to_dict(row: CoverImageCallLog) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "project_id": str(row.project_id),
        "llm_provider_id": str(row.llm_provider_id),
        "provider_name": row.provider_name,
        "model_name": row.model_name,
        "prompt": row.prompt,
        "size": row.size,
        "quality": row.quality,
        "store_compressed": row.store_compressed,
        "status": row.status,
        "http_status": row.http_status,
        "error_message": row.error_message,
        "duration_ms": row.duration_ms,
        "response_kind": row.response_kind,
        "gateway_url": row.gateway_url,
        "debug_bundle_rel_path": row.debug_bundle_rel_path,
        "result_cover_url": row.result_cover_url,
    }


def list_cover_image_calls(
    db: Session,
    *,
    limit: int = 200,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    project_id: Optional[UUID] = None,
) -> List[Dict[str, Any]]:
    q = db.query(CoverImageCallLog)
    if since is not None:
        q = q.filter(CoverImageCallLog.created_at >= since)
    if until is not None:
        q = q.filter(CoverImageCallLog.created_at <= until)
    if project_id is not None:
        q = q.filter(CoverImageCallLog.project_id == project_id)
    rows = (
        q.order_by(CoverImageCallLog.created_at.desc())
        .limit(max(1, min(limit, 2000)))
        .all()
    )
    return [_row_to_dict(r) for r in rows]
