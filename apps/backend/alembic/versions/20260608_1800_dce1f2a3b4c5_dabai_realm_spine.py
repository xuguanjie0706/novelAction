"""大白文境界脊柱：卷加 realm_start_rank/realm_end_rank，章加 realm_rank。

让境界成为有序、有区间、可校验的结构量，杜绝写作期境界乱跳/回退。

Revision ID: dce1f2a3b4c5
Revises: dcab12345678
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "dce1f2a3b4c5"
down_revision = "dcab12345678"
branch_labels = None
depends_on = None


def _has_col(inspector, table: str, col: str) -> bool:
    return any(c["name"] == col for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("dabai_volumes"):
        for col in ("realm_start_rank", "realm_end_rank"):
            if not _has_col(inspector, "dabai_volumes", col):
                op.add_column("dabai_volumes", sa.Column(col, sa.Integer(), nullable=True))
    if inspector.has_table("dabai_chapter_outlines"):
        if not _has_col(inspector, "dabai_chapter_outlines", "realm_rank"):
            op.add_column("dabai_chapter_outlines", sa.Column("realm_rank", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("dabai_chapter_outlines") and _has_col(inspector, "dabai_chapter_outlines", "realm_rank"):
        op.drop_column("dabai_chapter_outlines", "realm_rank")
    if inspector.has_table("dabai_volumes"):
        for col in ("realm_end_rank", "realm_start_rank"):
            if _has_col(inspector, "dabai_volumes", col):
                op.drop_column("dabai_volumes", col)
