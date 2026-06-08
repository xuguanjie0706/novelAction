"""新增大白文独立分支三表 dabai_projects / dabai_volumes / dabai_chapter_outlines。

与精品文主链路完全隔离，章纲表为爽点节拍器结构（无 choice_cost）。

Revision ID: d5e6f7a8b9c0
Revises: a4b5c6d7e8f9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "d5e6f7a8b9c0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("dabai_projects"):
        op.create_table(
            "dabai_projects",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("logline", sa.Text(), nullable=False),
            sa.Column("title", sa.String(length=120), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="generated"),
            sa.Column("mock", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("positioning", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
            sa.Column("golden_finger", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
            sa.Column("power_ladder", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
            sa.Column("factions", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("characters", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("storylines", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("linter_report", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
            sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
            sa.Column("failed_steps", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        )
        op.create_index("ix_dabai_projects_user_id", "dabai_projects", ["user_id"], unique=False)

    if not inspector.has_table("dabai_volumes"):
        op.create_table(
            "dabai_volumes",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("project_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("dabai_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("volume_number", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=True),
            sa.Column("phase", sa.String(length=20), nullable=True),
            sa.Column("planned_chapters", sa.Integer(), server_default="30"),
            sa.Column("big_beats", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("volume_climax", sa.Text(), nullable=True),
            sa.Column("end_hook", sa.Text(), nullable=True),
        )
        op.create_index("ix_dabai_volumes_project_id", "dabai_volumes", ["project_id"], unique=False)

    if not inspector.has_table("dabai_chapter_outlines"):
        op.create_table(
            "dabai_chapter_outlines",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("project_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("dabai_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("volume_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("dabai_volumes.id", ondelete="CASCADE"), nullable=True),
            sa.Column("chapter_number", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=120), nullable=True),
            # ── 爽点节拍器四拍（无 choice_cost）──
            sa.Column("shuang_type", sa.String(length=40), nullable=True),
            sa.Column("yaqu_setup", sa.Text(), nullable=True),
            sa.Column("yinbao", sa.Text(), nullable=True),
            sa.Column("shuang_payoff", sa.Text(), nullable=True),
            sa.Column("witnesses", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("end_hook", sa.Text(), nullable=True),
            sa.Column("new_info_count", sa.Integer(), server_default="1"),
            sa.Column("involved_characters", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
            sa.Column("is_big_beat", sa.Boolean(), server_default=sa.text("false")),
            sa.Column("expected_words", sa.Integer(), server_default="2000"),
        )
        op.create_index("ix_dabai_chapter_outlines_project_id",
                        "dabai_chapter_outlines", ["project_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("dabai_chapter_outlines"):
        op.drop_index("ix_dabai_chapter_outlines_project_id", table_name="dabai_chapter_outlines")
        op.drop_table("dabai_chapter_outlines")
    if inspector.has_table("dabai_volumes"):
        op.drop_index("ix_dabai_volumes_project_id", table_name="dabai_volumes")
        op.drop_table("dabai_volumes")
    if inspector.has_table("dabai_projects"):
        op.drop_index("ix_dabai_projects_user_id", table_name="dabai_projects")
        op.drop_table("dabai_projects")
