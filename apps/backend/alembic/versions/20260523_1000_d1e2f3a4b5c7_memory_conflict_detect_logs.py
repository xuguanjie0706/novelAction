"""memory_conflict_detect_logs 表

Revision ID: d1e2f3a4b5c7
Revises: c4d5e6f7a8b9
Create Date: 2026-05-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "d1e2f3a4b5c7"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("memory_conflict_detect_logs"):
        return

    op.create_table(
        "memory_conflict_detect_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chapters.id"), nullable=True),
        sa.Column("trigger", sa.String(40), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ok"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_chunks_scanned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_call_log_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("llm_call_logs.id"), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "output_payload",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("ix_memory_conflict_detect_logs_project_id", "memory_conflict_detect_logs", ["project_id"])
    op.create_index("ix_memory_conflict_detect_logs_chapter_id", "memory_conflict_detect_logs", ["chapter_id"])
    op.create_index("ix_memory_conflict_detect_logs_trigger", "memory_conflict_detect_logs", ["trigger"])
    op.create_index("ix_memory_conflict_detect_logs_status", "memory_conflict_detect_logs", ["status"])
    op.create_index("ix_memory_conflict_detect_logs_created_at", "memory_conflict_detect_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_memory_conflict_detect_logs_created_at", table_name="memory_conflict_detect_logs")
    op.drop_index("ix_memory_conflict_detect_logs_status", table_name="memory_conflict_detect_logs")
    op.drop_index("ix_memory_conflict_detect_logs_trigger", table_name="memory_conflict_detect_logs")
    op.drop_index("ix_memory_conflict_detect_logs_chapter_id", table_name="memory_conflict_detect_logs")
    op.drop_index("ix_memory_conflict_detect_logs_project_id", table_name="memory_conflict_detect_logs")
    op.drop_table("memory_conflict_detect_logs")
