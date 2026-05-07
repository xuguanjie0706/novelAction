"""add gated_draft_attempts to chapters

Revision ID: e6f7a8b9c0d1
Revises: d1e2f3a4b5c6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "e6f7a8b9c0d1"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def upgrade() -> None:
    if not _has_column("chapters", "gated_draft_attempts"):
        op.add_column(
            "chapters",
            sa.Column("gated_draft_attempts", sa.Integer(), nullable=False, server_default="0"),
        )
        op.alter_column("chapters", "gated_draft_attempts", server_default=None)


def downgrade() -> None:
    if _has_column("chapters", "gated_draft_attempts"):
        op.drop_column("chapters", "gated_draft_attempts")
