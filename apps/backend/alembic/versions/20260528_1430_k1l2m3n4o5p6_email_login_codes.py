"""新增邮箱登录验证码表。

Revision ID: k1l2m3n4o5p6
Revises: e2f3a4b5c6d8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "k1l2m3n4o5p6"
down_revision = "e2f3a4b5c6d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("email_login_codes"):
        return

    op.create_table(
        "email_login_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_email_login_codes_email", "email_login_codes", ["email"], unique=False)
    op.create_index("ix_email_login_codes_expires_at", "email_login_codes", ["expires_at"], unique=False)
    op.create_index("ix_email_login_codes_used_at", "email_login_codes", ["used_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("email_login_codes"):
        return
    op.drop_index("ix_email_login_codes_used_at", table_name="email_login_codes")
    op.drop_index("ix_email_login_codes_expires_at", table_name="email_login_codes")
    op.drop_index("ix_email_login_codes_email", table_name="email_login_codes")
    op.drop_table("email_login_codes")
