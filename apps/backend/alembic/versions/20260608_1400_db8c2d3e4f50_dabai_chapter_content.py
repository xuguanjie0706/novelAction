"""大白文章纲增正文字段：dabai_chapter_outlines.content / status（写作期填充）。

Revision ID: db8c2d3e4f50
Revises: da7b1c2d3e4f
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "db8c2d3e4f50"
down_revision = "da7b1c2d3e4f"
branch_labels = None
depends_on = None


def _has_col(inspector, table: str, col: str) -> bool:
    return any(c["name"] == col for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("dabai_chapter_outlines"):
        return
    if not _has_col(inspector, "dabai_chapter_outlines", "content"):
        op.add_column("dabai_chapter_outlines", sa.Column("content", sa.Text(), nullable=True))
    if not _has_col(inspector, "dabai_chapter_outlines", "status"):
        op.add_column("dabai_chapter_outlines",
                      sa.Column("status", sa.String(length=20), server_default="planned"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("dabai_chapter_outlines"):
        return
    for col in ("status", "content"):
        if _has_col(inspector, "dabai_chapter_outlines", col):
            op.drop_column("dabai_chapter_outlines", col)
