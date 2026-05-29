"""图片生成积分：按次固定扣费（封面 / 人物立绘）。

与文本 LLM 的 token 计费分离；成功落库后扣费，失败不扣。
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.dependencies import is_admin_user
from app.models.user import User
from app.services import credit_service

logger = logging.getLogger(__name__)


def image_generation_cost() -> int:
    """单次图片生成应扣积分数（配置为 0 时不扣费）。"""
    return max(0, int(settings.CREDIT_IMAGE_GENERATION_COST))


def resolve_image_billing_user(current_user: User) -> Optional[UUID]:
    """解析应对图片生成扣费的用户；管理员 token 不扣费。"""
    if is_admin_user(current_user):
        return None
    return current_user.id


def preflight_image_generation(user_id: Optional[UUID], *, db: Session) -> None:
    """图片生成前预检：余额 ≤ 0 阻断；余额 > 0 允许（扣费后可透支）。"""
    if user_id is None or image_generation_cost() <= 0:
        return
    credit_service.preflight_billed_call(user_id, db=db)


def charge_image_generation(
    user_id: Optional[UUID],
    *,
    model: Optional[str],
    task: str,
    ref_id: Optional[str] = None,
    db: Session,
) -> None:
    """图片生成成功后扣费并 commit；扣费失败仅记日志，不推翻已落库的图片。"""
    cost = image_generation_cost()
    if user_id is None or cost <= 0:
        return
    try:
        credit_service.deduct(
            user_id,
            cost,
            model=model,
            task=task,
            ref_id=ref_id,
            ref_type="image_generation",
            note=f"图片生成 -{cost} 积分",
            db=db,
        )
        db.commit()
    except Exception as err:
        db.rollback()
        logger.warning("图片生成积分扣费失败 user_id=%s task=%s: %s", user_id, task, err)
