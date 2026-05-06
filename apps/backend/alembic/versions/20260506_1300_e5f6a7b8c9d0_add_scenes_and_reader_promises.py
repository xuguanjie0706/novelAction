"""add scenes and reader_promises tables (P2 三层调度 + 读者期待管理)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # scenes 表
    op.create_table(
        "scenes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("outline_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outline_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("time", sa.String(100), nullable=True),
        sa.Column("story_day", sa.String(50), nullable=True),
        sa.Column("location_name", sa.String(200), nullable=True),
        sa.Column("pov_character_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("characters_on_stage", sa.JSON(), nullable=True),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("conflict", sa.Text(), nullable=True),
        sa.Column("turn", sa.Text(), nullable=True),
        sa.Column("hook", sa.Text(), nullable=True),
        sa.Column("hook_strength", sa.Integer(), server_default="3", nullable=True),
        sa.Column("word_budget", sa.Integer(), server_default="400", nullable=True),
        sa.Column("actual_word_count", sa.Integer(), server_default="0", nullable=True),
        sa.Column("pacing", sa.String(20), server_default="mid", nullable=True),
        sa.Column("sensory_focus", sa.String(30), server_default="mixed", nullable=True),
        sa.Column("status", sa.String(20), server_default="planned", nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_scenes_project_order", "scenes", ["project_id", "order"])
    op.create_index("ix_scenes_chapter", "scenes", ["chapter_id"])

    # reader_promises 表
    op.create_table(
        "reader_promises",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("promise_text", sa.Text(), nullable=False),
        sa.Column("promise_type", sa.String(30), server_default="chapter_ending", nullable=True),
        sa.Column("source_chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_chapter_number", sa.Integer(), nullable=True),
        sa.Column("expected_chapter_window", sa.Integer(), nullable=True),
        sa.Column("expected_volume", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), server_default="open", nullable=True),
        sa.Column("fulfilled_chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fulfilled_chapter_number", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="3", nullable=True),
        sa.Column("audience_aware", sa.Integer(), server_default="3", nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_reader_promises_project_status", "reader_promises", ["project_id", "status"])
    op.create_index("ix_reader_promises_source_chapter", "reader_promises", ["source_chapter_id"])


def downgrade() -> None:
    op.drop_index("ix_reader_promises_source_chapter", table_name="reader_promises")
    op.drop_index("ix_reader_promises_project_status", table_name="reader_promises")
    op.drop_table("reader_promises")

    op.drop_index("ix_scenes_chapter", table_name="scenes")
    op.drop_index("ix_scenes_project_order", table_name="scenes")
    op.drop_table("scenes")
