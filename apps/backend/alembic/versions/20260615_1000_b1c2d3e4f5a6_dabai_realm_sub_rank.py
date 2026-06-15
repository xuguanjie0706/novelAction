"""大白文章纲：realm_sub_rank 同境内小层。

与 realm_rank 大境档配合，约束章纲 yinbao 战力通胀（炼气三重等细层）。

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "b1c2d3e4f5a6"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def _has_col(inspector, table: str, col: str) -> bool:
    return any(c["name"] == col for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("dabai_chapter_outlines"):
        if not _has_col(inspector, "dabai_chapter_outlines", "realm_sub_rank"):
            op.add_column(
                "dabai_chapter_outlines",
                sa.Column("realm_sub_rank", sa.Integer(), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("dabai_chapter_outlines") and _has_col(
        inspector, "dabai_chapter_outlines", "realm_sub_rank",
    ):
        op.drop_column("dabai_chapter_outlines", "realm_sub_rank")
