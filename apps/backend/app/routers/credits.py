"""用户积分路由。

资源边界：仅暴露当前登录用户自己的积分数据，禁止跨用户访问。

端点列表：
    GET  /api/v1/credits/me                  查询当前余额与统计
    GET  /api/v1/credits/me/transactions     查询积分流水（分页）
    POST /api/v1/credits/redeem              兑换码核销
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services import credit_service, redeem_code_service

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/me", response_model=Dict[str, Any])
def get_my_credits(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """查询当前登录用户的积分余额与累计统计。

    Returns:
        包含 ``user_id`` / ``balance`` / ``total_consumed`` / ``total_topped_up`` /
        ``tier_info`` 的字典；账户不存在时自动创建余额为 0 的账户。
    """
    credit = credit_service.get_or_create(current_user.id, db)
    db.commit()
    return {
        "user_id": str(credit.user_id),
        "balance": credit.balance,
        "total_consumed": credit.total_consumed,
        "total_topped_up": credit.total_topped_up,
        "updated_at": credit.updated_at.isoformat() if credit.updated_at else None,
        # 费率参考信息（前端展示用）
        "rate_info": {
            "heavy":    {"input_per_1k": 5,  "output_per_1k": 15,  "desc": "GPT-4 / Claude Opus / Gemini Pro"},
            "standard": {"input_per_1k": 1,  "output_per_1k": 3,   "desc": "GPT-3.5 / Qwen-Plus / Gemini Flash"},
            "light":    {"input_per_1k": 0,  "output_per_1k": 0,   "desc": "本地模型（免费）"},
        },
    }


@router.get("/me/transactions", response_model=List[Dict[str, Any]])
def get_my_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """查询当前登录用户的积分流水（按时间倒序）。

    Args:
        limit: 每页条数（1-200，默认 50）。
        offset: 分页偏移（默认 0）。

    Returns:
        流水字典列表，每条含 id / delta / balance_after / ref_type / model /
        prompt_tokens / completion_tokens / task / note / created_at。
    """
    return credit_service.list_transactions(current_user.id, limit=limit, offset=offset, db=db)


# ──────────────────────────────────────────────
# 兑换码核销
# ──────────────────────────────────────────────

class RedeemRequest(BaseModel):
    """兑换码请求体。"""
    code: str = Field(..., min_length=1, max_length=40, description="兑换码字符串（可含空格；16 位可无连字符）")


_REDEEM_ERROR_MAP = {
    "CODE_NOT_FOUND":    (404, "兑换码不存在"),
    "CODE_DISABLED":     (410, "兑换码已被禁用"),
    "CODE_EXPIRED":      (410, "兑换码已过期"),
    "CODE_ALREADY_USED": (409, "兑换码已被使用"),
}


@router.post("/redeem", response_model=Dict[str, Any])
def redeem_code(
    body: RedeemRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """核销兑换码，将面值积分充入当前用户账户。

    Args:
        body: 包含 ``code`` 字段的请求体（大小写不敏感）。

    Returns:
        包含 ``code`` / ``credits`` / ``balance_after`` 的兑换结果字典。

    Raises:
        HTTPException 404: 码不存在。
        HTTPException 409: 码已被使用。
        HTTPException 410: 码已禁用或已过期。
    """
    try:
        result = redeem_code_service.redeem(body.code, current_user.id, db=db)
        db.commit()
        return result
    except ValueError as exc:
        status_code, detail = _REDEEM_ERROR_MAP.get(str(exc), (400, str(exc)))
        raise HTTPException(status_code=status_code, detail=detail)
