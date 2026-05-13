"""兑换码模型。

职责：
- ``RedeemCode``：每行代表一张兑换码，记录面值、状态与核销信息。

设计约定：
- ``code`` 为唯一字符串，格式 ``XXXX-XXXX-XXXX-XXXX``（大写字母+数字，共 16 位+3 连字符）。
- ``status`` 枚举值：
    - ``active``    可用（未使用）
    - ``redeemed``  已兑换
    - ``disabled``  管理员手动禁用
- ``batch_id`` 用于将同一批次生成的码归组，便于管理员查询/撤销整批。
- ``credits`` 以整数「积分」存储，与 ``UserCredit.balance`` 单位一致。

禁止事项：不要直接修改本表状态，统一走 ``services/redeem_code_service.py``。
"""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class RedeemCode(Base):
    """兑换码实体。

    Attributes:
        id: UUID 主键。
        code: 唯一兑换码字符串（大写字母+数字，带连字符格式）。
        credits: 兑换面值（积分数，正整数）。
        status: 当前状态（active / redeemed / disabled）。
        batch_id: 批次标识，同批次码共享此值（可选）。
        note: 管理员备注（批次说明、活动名称等）。
        redeemed_by: 核销用户 UUID（核销后填入）。
        redeemed_at: 核销时间（UTC）。
        expires_at: 过期时间（UTC）；为空表示永不过期。
        created_at: 生成时间（UTC）。
    """

    __tablename__ = "redeem_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(32), unique=True, nullable=False, index=True)

    # 面值
    credits = Column(BigInteger, nullable=False)

    # 状态：active / redeemed / disabled
    status = Column(String(20), nullable=False, default="active", index=True)

    # 批次信息
    batch_id = Column(String(64), nullable=True, index=True)
    note = Column(Text, nullable=True)

    # 核销信息（兑换后填入）
    redeemed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    redeemed_at = Column(DateTime(timezone=True), nullable=True)

    # 有效期（NULL = 永久有效）
    expires_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        # 常用查询：按批次列出 + 按状态过滤
        Index("ix_redeem_code_batch_status", "batch_id", "status"),
    )
