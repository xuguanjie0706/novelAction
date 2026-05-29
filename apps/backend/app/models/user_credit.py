"""用户积分模型。

职责：
- ``UserCredit``：每用户一行，存储当前余额与累计统计，是积分系统的「账本」。
- ``CreditTransaction``：每次积分变动产生一行流水，是不可变的审计记录。

设计约定：
- 余额以整数「积分」存储，避免浮点误差；换算精度在 credit_service 层处理（向上取整）。
- ``ref_type`` 枚举值：
    - ``registration_bonus``  注册赠送
    - ``llm_call``            文本 AI 调用自动扣费
    - ``image_generation``    图片生成按次扣费（封面 / 立绘）
    - ``admin_topup``         管理员充值
    - ``admin_adjust``        管理员任意调整（可正可负，附 note）
    - ``redeem_code``         兑换码核销入账
- ``delta`` 正值为入账，负值为出账；``balance_after`` 为变动后余额的快照，便于对账。

禁止事项：不要直接操作这两张表，统一走 ``services/credit_service.py``。
"""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class UserCredit(Base):
    """用户积分账户。

    Attributes:
        id: UUID 主键。
        user_id: 关联 users.id（唯一，一人一账户）。
        balance: 当前可用余额（积分）；计费可透支为负，充值时自动抵扣欠款。
        total_consumed: 历史累计消耗积分（只增不减）。
        total_topped_up: 历史累计充值 / 赠送积分（只增不减）。
        created_at / updated_at: UTC 时间戳。
    """

    __tablename__ = "user_credits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    balance = Column(BigInteger, nullable=False, default=0)
    total_consumed = Column(BigInteger, nullable=False, default=0)
    total_topped_up = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CreditTransaction(Base):
    """积分变动流水（不可变审计记录）。

    Attributes:
        id: UUID 主键。
        user_id: 关联 users.id。
        delta: 本次变动量（正=入账，负=出账）。
        balance_after: 变动后余额快照，便于逐行对账。
        ref_type: 来源类型，见模块级文档中的枚举说明。
        ref_id: 关联业务主键（如 llm_call_logs.id）；可为空。
        model: AI 调用时使用的模型名。
        prompt_tokens: AI 调用的输入 token 数。
        completion_tokens: AI 调用的输出 token 数。
        task: AI 调用任务名（来自 llm_task_profiles）。
        note: 管理员备注或系统说明。
        created_at: 记录创建时间（UTC）。
    """

    __tablename__ = "credit_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    delta = Column(BigInteger, nullable=False)          # 正=充值，负=扣费
    balance_after = Column(BigInteger, nullable=False)  # 变动后余额快照

    # 来源
    ref_type = Column(String(40), nullable=False)   # registration_bonus / llm_call / admin_topup / admin_adjust
    ref_id = Column(String(100), nullable=True)     # 关联业务主键

    # AI 调用专属字段（ref_type=llm_call 时填入）
    model = Column(String(200), nullable=True)
    prompt_tokens = Column(BigInteger, nullable=True)
    completion_tokens = Column(BigInteger, nullable=True)
    task = Column(String(100), nullable=True)

    note = Column(Text, nullable=True)  # 管理员备注
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        # 按用户 + 时间倒序查流水的常用查询
        Index("ix_credit_txn_user_created", "user_id", "created_at"),
    )
