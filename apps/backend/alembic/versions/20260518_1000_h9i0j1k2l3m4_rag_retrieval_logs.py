"""rag_retrieval_logs 表

Revision ID: h9i0j1k2l3m4
Revises: c1d2e3f4a5b6
Create Date: 2026-05-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "h9i0j1k2l3m4"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rag_retrieval_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chapters.id"), nullable=True),
        sa.Column("source", sa.String(40), nullable=False, server_default="rag_query"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ok"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_payload", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("output_payload", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("ix_rag_retrieval_logs_project_id", "rag_retrieval_logs", ["project_id"])
    op.create_index("ix_rag_retrieval_logs_chapter_id", "rag_retrieval_logs", ["chapter_id"])
    op.create_index("ix_rag_retrieval_logs_source", "rag_retrieval_logs", ["source"])
    op.create_index("ix_rag_retrieval_logs_created_at", "rag_retrieval_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_rag_retrieval_logs_created_at", table_name="rag_retrieval_logs")
    op.drop_index("ix_rag_retrieval_logs_source", table_name="rag_retrieval_logs")
    op.drop_index("ix_rag_retrieval_logs_chapter_id", table_name="rag_retrieval_logs")
    op.drop_index("ix_rag_retrieval_logs_project_id", table_name="rag_retrieval_logs")
    op.drop_table("rag_retrieval_logs")
