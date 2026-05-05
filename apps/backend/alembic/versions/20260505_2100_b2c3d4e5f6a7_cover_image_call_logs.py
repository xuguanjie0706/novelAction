"""cover_image_call_logs：封面图片网关调用审计

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-05 21:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cover_image_call_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("llm_provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("llm_providers.id"), nullable=False),
        sa.Column("provider_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("model_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("size", sa.String(32), nullable=False, server_default=""),
        sa.Column("quality", sa.String(20), nullable=False, server_default=""),
        sa.Column("store_compressed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_kind", sa.String(20), nullable=False, server_default=""),
        sa.Column("gateway_url", sa.String(2000), nullable=False, server_default=""),
        sa.Column("debug_bundle_rel_path", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("ix_cover_image_call_logs_project_id", "cover_image_call_logs", ["project_id"])
    op.create_index("ix_cover_image_call_logs_llm_provider_id", "cover_image_call_logs", ["llm_provider_id"])
    op.create_index("ix_cover_image_call_logs_created_at", "cover_image_call_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_cover_image_call_logs_created_at", table_name="cover_image_call_logs")
    op.drop_index("ix_cover_image_call_logs_llm_provider_id", table_name="cover_image_call_logs")
    op.drop_index("ix_cover_image_call_logs_project_id", table_name="cover_image_call_logs")
    op.drop_table("cover_image_call_logs")
