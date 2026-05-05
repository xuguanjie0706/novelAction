"""chapter_debrief_apply_records 复盘落库审计

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chapter_debrief_apply_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("apply_source", sa.String(32), nullable=False, server_default="manual_tab"),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_chapter_debrief_apply_chapter_created",
        "chapter_debrief_apply_records",
        ["chapter_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chapter_debrief_apply_chapter_created", table_name="chapter_debrief_apply_records")
    op.drop_table("chapter_debrief_apply_records")
