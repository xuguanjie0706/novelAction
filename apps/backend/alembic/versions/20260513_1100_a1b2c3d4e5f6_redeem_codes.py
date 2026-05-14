"""兑换码系统：redeem_codes 表

Revision ID: g8h9i0j1k2l3
Revises: f4a5b6c7d8e9

变更：
1. 新增 ``redeem_codes`` 表：存储兑换码及其核销状态。
2. 建立复合索引 (batch_id, status) 支持批次管理查询。

字段说明：
- ``code``：唯一兑换码字符串，格式 XXXX-XXXX-XXXX-XXXX。
- ``credits``：积分面值，BIGINT，与 user_credits.balance 同单位。
- ``status``：active / redeemed / disabled，默认 active。
- ``batch_id``：批次标识，同批次码共享，便于管理员批量查询。
- ``redeemed_by``：核销用户 UUID，FK users.id ON DELETE SET NULL。
- ``expires_at``：过期时间（NULL = 永久有效）。

downgrade：直接 DROP redeem_codes 表。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "g8h9i0j1k2l3"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "redeem_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("credits", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("batch_id", sa.String(64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "redeemed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 唯一索引：code
    op.create_index("ix_redeem_codes_code", "redeem_codes", ["code"], unique=True)
    # 状态索引
    op.create_index("ix_redeem_codes_status", "redeem_codes", ["status"], unique=False)
    # 复合索引：按批次 + 状态查询
    op.create_index(
        "ix_redeem_code_batch_status",
        "redeem_codes",
        ["batch_id", "status"],
        unique=False,
    )
    # redeemed_by 索引（查某用户的兑换记录）
    op.create_index(
        "ix_redeem_codes_redeemed_by",
        "redeem_codes",
        ["redeemed_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_redeem_codes_redeemed_by", table_name="redeem_codes")
    op.drop_index("ix_redeem_code_batch_status", table_name="redeem_codes")
    op.drop_index("ix_redeem_codes_status", table_name="redeem_codes")
    op.drop_index("ix_redeem_codes_code", table_name="redeem_codes")
    op.drop_table("redeem_codes")
