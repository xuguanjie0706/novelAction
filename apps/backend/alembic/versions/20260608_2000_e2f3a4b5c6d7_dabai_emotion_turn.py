"""大白文章纲加转折拍：dabai_chapter_outlines.emotion_turn（情绪扳机）。

补齐爽点节拍器缺失的「转」拍，让情绪扳机在排章纲时就预设，正文不再现编。

Revision ID: e2f3a4b5c6d7
Revises: dce1f2a3b4c5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "e2f3a4b5c6d7"
down_revision = "dce1f2a3b4c5"
branch_labels = None
depends_on = None


def _has_col(inspector, table: str, col: str) -> bool:
    return any(c["name"] == col for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("dabai_chapter_outlines") and not _has_col(
        inspector, "dabai_chapter_outlines", "emotion_turn"
    ):
        op.add_column("dabai_chapter_outlines", sa.Column("emotion_turn", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("dabai_chapter_outlines") and _has_col(
        inspector, "dabai_chapter_outlines", "emotion_turn"
    ):
        op.drop_column("dabai_chapter_outlines", "emotion_turn")
