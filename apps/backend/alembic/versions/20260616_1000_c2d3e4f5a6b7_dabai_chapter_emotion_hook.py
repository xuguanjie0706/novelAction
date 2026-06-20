"""大白文章纲：target_emotion 目标情绪 + hook_type 章尾钩子类型。

借鉴 story-long-write「情绪先于故事 + 命名钩子库」：把每章交付的情绪与
章尾钩子类型升为一等公民字段，供章纲 prompt 注入、linter 轮换闸门、写章注入。

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def _has_col(inspector, table: str, col: str) -> bool:
    return any(c["name"] == col for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("dabai_chapter_outlines"):
        return
    if not _has_col(inspector, "dabai_chapter_outlines", "target_emotion"):
        op.add_column(
            "dabai_chapter_outlines",
            sa.Column("target_emotion", sa.String(length=40), nullable=True),
        )
    if not _has_col(inspector, "dabai_chapter_outlines", "hook_type"):
        op.add_column(
            "dabai_chapter_outlines",
            sa.Column("hook_type", sa.String(length=40), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("dabai_chapter_outlines"):
        return
    for col in ("hook_type", "target_emotion"):
        if _has_col(inspector, "dabai_chapter_outlines", col):
            op.drop_column("dabai_chapter_outlines", col)
