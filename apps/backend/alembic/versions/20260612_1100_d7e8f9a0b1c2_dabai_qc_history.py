"""dabai 质检报告历史化：追加落库 + 回归字段。

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "d7e8f9a0b1c2"
down_revision = "c6d7e8f9a0b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("dabai_quality_reports"):
        return
    cols = {c["name"] for c in inspector.get_columns("dabai_quality_reports")}
    if "source" not in cols:
        op.add_column(
            "dabai_quality_reports",
            sa.Column("source", sa.String(30), server_default="manual", nullable=False),
        )
    if "content_word_count" not in cols:
        op.add_column("dabai_quality_reports", sa.Column("content_word_count", sa.Integer()))
    if "content_head_preview" not in cols:
        op.add_column("dabai_quality_reports", sa.Column("content_head_preview", sa.Text()))
    op.create_index(
        "ix_dabai_qc_project_chapter_created",
        "dabai_quality_reports",
        ["project_id", "chapter_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_dabai_qc_project_chapter_created", table_name="dabai_quality_reports")
    inspector = inspect(op.get_bind())
    if not inspector.has_table("dabai_quality_reports"):
        return
    cols = {c["name"] for c in inspector.get_columns("dabai_quality_reports")}
    for name in ("content_head_preview", "content_word_count", "source"):
        if name in cols:
            op.drop_column("dabai_quality_reports", name)
