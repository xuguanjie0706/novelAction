"""cover_image_call_logs.result_cover_url 预览用

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cover_image_call_logs",
        sa.Column("result_cover_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cover_image_call_logs", "result_cover_url")
