"""chapter_analysis_records — 章节追读/钩子分析历史记录表

每次点「分析」写入一条，前端展示各章均值（avg_score / avg_hook_strength）。

Revision ID: c0d1e2f3a4b5
Revises: a8b9c0d1e2f3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "c0d1e2f3a4b5"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chapter_analysis_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", UUID(as_uuid=True), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        # 追读模拟
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("will_continue", sa.Boolean, nullable=False),
        sa.Column("drop_risk", sa.String(20), nullable=False),
        sa.Column("what_hooked", sa.Text, server_default=""),
        sa.Column("what_repelled", sa.Text, server_default=""),
        sa.Column("verdict", sa.Text, server_default=""),
        sa.Column("hook_tail", sa.Text, server_default=""),
        # 钩子检测
        sa.Column("hook_type", sa.String(30), nullable=False),
        sa.Column("hook_strength", sa.Integer, nullable=False),
        sa.Column("hook_analysis", sa.Text, server_default=""),
        sa.Column("hook_suggestions", JSONB, server_default="[]"),
        sa.Column("matched_promises_json", JSONB, server_default="[]"),
        # 时间戳
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_car_project_id", "chapter_analysis_records", ["project_id"])
    op.create_index("ix_car_chapter_id", "chapter_analysis_records", ["chapter_id"])
    op.create_index("ix_car_chapter_created", "chapter_analysis_records", ["chapter_id", "created_at"])


def downgrade() -> None:
    op.drop_table("chapter_analysis_records")
