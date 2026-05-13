"""管理员兑换码路由。

资源边界：需要 admin token（role=admin）。

端点列表：
    POST /api/v1/admin/redeem-codes/batch       批量生成兑换码
    GET  /api/v1/admin/redeem-codes             列出所有码（可按批次/状态过滤）
    GET  /api/v1/admin/redeem-codes/batches     列出批次摘要
    PATCH /api/v1/admin/redeem-codes/{id}/disable  禁用单张码
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, is_admin_user
from app.models.user import User
from app.services import redeem_code_service

router = APIRouter(prefix="/admin/redeem-codes", tags=["admin-redeem-codes"])


def _require_admin(current_user: User = Depends(get_current_user)) -> User:
    """确认请求方持有管理员 token。

    Raises:
        HTTPException 403: 非管理员 token。
    """
    if not is_admin_user(current_user):
        raise HTTPException(status_code=403, detail="仅管理员可访问")
    return current_user


# ──────────────────────────────────────────────
# Request Schemas
# ──────────────────────────────────────────────

class BatchGenerateRequest(BaseModel):
    """批量生成兑换码请求体。"""
    count: int = Field(..., ge=1, le=1000, description="生成数量（1-1000）")
    credits: int = Field(..., gt=0, description="每张码的积分面值（> 0）")
    note: Optional[str] = Field(None, max_length=200, description="批次备注（活动名称等）")
    expires_days: Optional[int] = Field(
        None, ge=1, le=3650,
        description="有效期天数（从生成时刻起算）；不填表示永久有效",
    )


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.post("/batch", response_model=Dict[str, Any])
def batch_generate(
    body: BatchGenerateRequest,
    _admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """批量生成兑换码。

    Args:
        body: 生成参数（数量、面值、备注、有效期）。

    Returns:
        包含 ``batch_id`` / ``count`` / ``credits`` / ``codes``（字符串列表）的字典。
    """
    from datetime import datetime, timedelta, timezone

    expires_at = None
    if body.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_days)

    codes = redeem_code_service.generate_batch(
        count=body.count,
        credits=body.credits,
        note=body.note,
        expires_at=expires_at,
        db=db,
    )
    db.flush()  # 获取 batch_id（所有码共享同一 batch_id）
    db.commit()

    return {
        "batch_id": codes[0].batch_id,
        "count": len(codes),
        "credits": body.credits,
        "note": body.note,
        "expires_at": codes[0].expires_at.isoformat() if codes[0].expires_at else None,
        "codes": [c.code for c in codes],
    }


@router.get("/batches", response_model=List[Dict[str, Any]])
def list_batches(
    _admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """列出批次摘要（按最新创建时间倒序）。

    Returns:
        每条含 batch_id / credits / note / total / active_count / redeemed_count /
        created_at / expires_at。
    """
    return redeem_code_service.list_batches(db=db)


@router.get("", response_model=List[Dict[str, Any]])
def list_codes(
    batch_id: Optional[str] = Query(None, description="按批次过滤"),
    status: Optional[str] = Query(None, description="按状态过滤（active/redeemed/disabled）"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """分页查询兑换码列表。

    Args:
        batch_id: 可选批次过滤。
        status: 可选状态过滤。
        limit / offset: 分页参数。

    Returns:
        码列表，每条含 id / code / credits / status / batch_id / note /
        redeemed_by / redeemed_at / expires_at / created_at。
    """
    return redeem_code_service.list_codes(
        batch_id=batch_id,
        status=status,
        limit=limit,
        offset=offset,
        db=db,
    )


@router.patch("/{code_id}/disable", response_model=Dict[str, Any])
def disable_code(
    code_id: UUID,
    _admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """禁用指定兑换码（已核销的码不可禁用）。

    Args:
        code_id: 码的 UUID。

    Returns:
        更新后的码状态字典。

    Raises:
        HTTPException 404: 码不存在。
        HTTPException 409: 码已被核销，无需禁用。
    """
    try:
        obj = redeem_code_service.disable(code_id, db=db)
        db.commit()
        return redeem_code_service._to_dict(obj)
    except ValueError as exc:
        msg = str(exc)
        if msg == "CODE_NOT_FOUND":
            raise HTTPException(status_code=404, detail="兑换码不存在")
        if msg == "CODE_ALREADY_USED":
            raise HTTPException(status_code=409, detail="该码已被核销，无法禁用")
        raise HTTPException(status_code=400, detail=msg)
