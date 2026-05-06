"""pre_write_warning_records — 写前预警历史

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pre_write_warning_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", UUID(as_uuid=True), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_number", sa.Integer, nullable=False, server_default="0"),
        sa.Column("chapter_plan_summary", sa.Text, nullable=False, server_default=""),
        sa.Column("model_profile", sa.String(20), nullable=False, server_default="local"),
        sa.Column("llm_provider_id", sa.String(36), nullable=True),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pwwr_project_id", "pre_write_warning_records", ["project_id"])
    op.create_index("ix_pwwr_chapter_id", "pre_write_warning_records", ["chapter_id"])
    op.create_index("ix_pwwr_chapter_created", "pre_write_warning_records", ["chapter_id", "created_at"])


def downgrade() -> None:
    op.drop_table("pre_write_warning_records")
