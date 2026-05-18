from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.llm_call_log import clear_llm_calls, get_llm_call, list_llm_calls

router = APIRouter(prefix="/admin/llm-calls", tags=["admin-llm-calls"])


@router.get("/")
def list_calls(
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    since: Optional[datetime] = Query(default=None, description="含该时刻起（ISO8601）"),
    until: Optional[datetime] = Query(default=None, description="含该时刻止（ISO8601）"),
    include_payload: bool = Query(
        default=False,
        description="为 true 时返回全量 input/output（数据量大，仅调试）",
    ),
    db: Session = Depends(get_db),
):
    return list_llm_calls(
        page=page,
        page_size=page_size,
        since=since,
        until=until,
        include_payload=include_payload,
        db=db,
    )


@router.get("/{call_id}")
def get_call(call_id: UUID, db: Session = Depends(get_db)):
    """单条详情（含全量 input/output），供管理后台「查看」弹窗使用。"""
    row = get_llm_call(call_id, db=db)
    if row is None:
        raise HTTPException(status_code=404, detail="调用记录不存在")
    return row


@router.delete("/")
def clear_calls(db: Session = Depends(get_db)):
    deleted = clear_llm_calls(db=db)
    return {"deleted": deleted}
