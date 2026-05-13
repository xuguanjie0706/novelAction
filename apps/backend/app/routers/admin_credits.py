"""管理员积分管理路由。

资源边界：需要 admin token（role=admin），可跨用户操作积分账户。

端点列表：
    GET  /api/v1/admin/credits                 分页列出所有用户积分账户
    GET  /api/v1/admin/credits/{user_id}       查询指定用户余额
    GET  /api/v1/admin/credits/{user_id}/transactions  查询指定用户流水
    POST /api/v1/admin/credits/{user_id}/topup         充值
    POST /api/v1/admin/credits/{user_id}/adjust        调账（正/负均可）
"""

from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, is_admin_user
from app.models.user import User
from app.services import credit_service

router = APIRouter(prefix="/admin/credits", tags=["admin-credits"])


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

class TopupRequest(BaseModel):
    """充值请求体。"""
    amount: int = Field(..., gt=0, description="充值积分数，必须 > 0")
    note: str | None = Field(None, description="管理员备注（可选）")


class AdjustRequest(BaseModel):
    """调账请求体（正=加分，负=扣分）。"""
    delta: int = Field(..., description="调整量，非零整数；正=加分，负=扣分")
    note: str | None = Field(None, description="调账原因（建议必填）")


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.get("", response_model=List[Dict[str, Any]])
def list_all_credits(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """分页列出所有注册用户的积分视图（按余额倒序）。

    以 ``users`` 为主表左连接 ``user_credits``：从未触发过积分写路径的用户
    在库中可能尚无 ``user_credits`` 行，此时仍列出该用户，余额与统计字段为 0，
    时间戳为空；管理员可对其充值以懒创建账户行。

    Args:
        limit: 每页条数（1-500，默认 100）。
        offset: 分页偏移。

    Returns:
        账户列表，每条含 user_id / balance / total_consumed / total_topped_up /
        created_at / updated_at，并附带用户 email / username（JOIN users 表）。
    """
    from app.models.user_credit import UserCredit
    from app.models.user import User as UserModel

    rows = (
        db.query(UserModel, UserCredit)
        .outerjoin(UserCredit, UserCredit.user_id == UserModel.id)
        .order_by(sa_func.coalesce(UserCredit.balance, 0).desc())
        .offset(offset)
        .limit(max(1, min(limit, 500)))
        .all()
    )
    result = []
    for user, credit in rows:
        result.append({
            "user_id": str(user.id),
            "email": user.email,
            "username": user.username,
            "balance": credit.balance if credit else 0,
            "total_consumed": credit.total_consumed if credit else 0,
            "total_topped_up": credit.total_topped_up if credit else 0,
            "created_at": credit.created_at.isoformat() if credit and credit.created_at else None,
            "updated_at": credit.updated_at.isoformat() if credit and credit.updated_at else None,
        })
    return result


@router.get("/{user_id}", response_model=Dict[str, Any])
def get_user_credits(
    user_id: UUID,
    _admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """查询指定用户的积分账户。

    Args:
        user_id: 目标用户 UUID。

    Returns:
        账户信息字典；用户不存在积分账户时返回 balance=0 的虚拟记录。
    """
    balance = credit_service.get_balance(user_id, db=db)
    from app.models.user_credit import UserCredit
    credit = db.query(UserCredit).filter(UserCredit.user_id == user_id).first()
    return {
        "user_id": str(user_id),
        "balance": balance,
        "total_consumed": credit.total_consumed if credit else 0,
        "total_topped_up": credit.total_topped_up if credit else 0,
        "updated_at": credit.updated_at.isoformat() if credit and credit.updated_at else None,
    }


@router.get("/{user_id}/transactions", response_model=List[Dict[str, Any]])
def get_user_transactions(
    user_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """查询指定用户的积分流水（按时间倒序）。"""
    return credit_service.list_transactions(user_id, limit=limit, offset=offset, db=db)


@router.post("/{user_id}/topup", response_model=Dict[str, Any])
def topup_user_credits(
    user_id: UUID,
    body: TopupRequest,
    _admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """为指定用户充值积分。

    Args:
        user_id: 目标用户 UUID。
        body: 充值请求体（amount > 0，可附备注）。

    Returns:
        充值后的最新余额与流水摘要。
    """
    txn = credit_service.topup(
        user_id,
        body.amount,
        ref_type="admin_topup",
        note=body.note,
        db=db,
    )
    db.commit()
    return {
        "user_id": str(user_id),
        "delta": txn.delta,
        "balance_after": txn.balance_after,
        "ref_type": txn.ref_type,
        "note": txn.note,
        "created_at": txn.created_at.isoformat() if txn.created_at else None,
    }


@router.post("/{user_id}/adjust", response_model=Dict[str, Any])
def adjust_user_credits(
    user_id: UUID,
    body: AdjustRequest,
    _admin: User = Depends(_require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """管理员手动调整用户积分（正=加分，负=扣分）。

    余额不会产生负值（穿透到 0 为止）。

    Args:
        user_id: 目标用户 UUID。
        body: 调账请求体（delta 非零，建议附 note 说明原因）。

    Returns:
        调账后的最新余额与流水摘要。

    Raises:
        HTTPException 400: delta == 0。
    """
    if body.delta == 0:
        raise HTTPException(status_code=400, detail="delta 不能为 0")
    txn = credit_service.admin_adjust(user_id, body.delta, note=body.note, db=db)
    db.commit()
    return {
        "user_id": str(user_id),
        "delta": txn.delta,
        "balance_after": txn.balance_after,
        "ref_type": txn.ref_type,
        "note": txn.note,
        "created_at": txn.created_at.isoformat() if txn.created_at else None,
    }
