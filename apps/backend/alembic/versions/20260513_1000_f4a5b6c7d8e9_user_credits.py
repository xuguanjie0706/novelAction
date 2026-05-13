"""用户积分系统：user_credits + credit_transactions 两张表

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8

变更：
1. 新增 ``user_credits`` 表：每用户一行，存储积分余额与累计统计。
2. 新增 ``credit_transactions`` 表：积分变动流水，含联合索引 (user_id, created_at)。

设计说明：
- 余额以 BIGINT 存储，单位「积分」，避免浮点精度问题。
- ``credit_transactions.ref_type`` 枚举：
    registration_bonus / llm_call / admin_topup / admin_adjust
- downgrade 按依赖顺序反向 DROP（transactions 先于 credits）。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = "f4a5b6c7d8e9"
down_revision = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── user_credits ──────────────────────────────────────────
    op.create_table(
        "user_credits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("balance", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_consumed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_topped_up", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_user_credits_user_id", "user_credits", ["user_id"])

    # ── credit_transactions ────────────────────────────────────
    op.create_table(
        "credit_transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("delta", sa.BigInteger(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("ref_type", sa.String(40), nullable=False),
        sa.Column("ref_id", sa.String(100), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("prompt_tokens", sa.BigInteger(), nullable=True),
        sa.Column("completion_tokens", sa.BigInteger(), nullable=True),
        sa.Column("task", sa.String(100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            index=True,
        ),
    )
    op.create_index(
        "ix_credit_txn_user_id", "credit_transactions", ["user_id"]
    )
    op.create_index(
        "ix_credit_txn_user_created",
        "credit_transactions",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_credit_txn_user_created", table_name="credit_transactions")
    op.drop_index("ix_credit_txn_user_id", table_name="credit_transactions")
    op.drop_table("credit_transactions")

    op.drop_index("ix_user_credits_user_id", table_name="user_credits")
    op.drop_table("user_credits")
