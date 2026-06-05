"""新增质检根因台账表 quality_root_cause_logs。

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "a4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("quality_root_cause_logs"):
        return

    op.create_table(
        "quality_root_cause_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chapters.id"), nullable=True),
        sa.Column("source_chapter_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_id", sa.String(length=36), nullable=False, server_default=""),
        sa.Column("item_kind", sa.String(length=20), nullable=False, server_default="dimension"),
        sa.Column("dimension", sa.String(length=60), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("problem_summary", sa.Text(), nullable=False),
        sa.Column("root_cause_category", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("root_cause_detail", sa.Text(), nullable=True),
        sa.Column("code_fix_suggestion", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("analysis_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint(
            "project_id", "chapter_id", "fingerprint",
            name="uq_quality_root_cause_project_chapter_fingerprint",
        ),
    )
    op.create_index(
        "ix_quality_root_cause_logs_project_id",
        "quality_root_cause_logs", ["project_id"], unique=False,
    )
    op.create_index(
        "ix_quality_root_cause_logs_category",
        "quality_root_cause_logs", ["root_cause_category"], unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("quality_root_cause_logs"):
        return
    op.drop_index("ix_quality_root_cause_logs_category", table_name="quality_root_cause_logs")
    op.drop_index("ix_quality_root_cause_logs_project_id", table_name="quality_root_cause_logs")
    op.drop_table("quality_root_cause_logs")
