"""新增大纲问题台账表 outline_issue_logs。

Revision ID: f3a4b5c6d7e8
Revises: k1l2m3n4o5p6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "f3a4b5c6d7e8"
down_revision = "k1l2m3n4o5p6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("outline_issue_logs"):
        return

    op.create_table(
        "outline_issue_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("volume_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outline_nodes.id"), nullable=True),
        sa.Column("rule_id", sa.String(length=40), nullable=False),
        sa.Column("dimension", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="linter"),
        sa.Column("field", sa.String(length=80), nullable=True),
        sa.Column("chapter_number", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint(
            "project_id", "volume_node_id", "fingerprint",
            name="uq_outline_issue_project_volume_fingerprint",
        ),
    )
    op.create_index("ix_outline_issue_logs_project_id", "outline_issue_logs", ["project_id"], unique=False)
    op.create_index("ix_outline_issue_logs_rule_id", "outline_issue_logs", ["rule_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("outline_issue_logs"):
        return
    op.drop_index("ix_outline_issue_logs_rule_id", table_name="outline_issue_logs")
    op.drop_index("ix_outline_issue_logs_project_id", table_name="outline_issue_logs")
    op.drop_table("outline_issue_logs")
