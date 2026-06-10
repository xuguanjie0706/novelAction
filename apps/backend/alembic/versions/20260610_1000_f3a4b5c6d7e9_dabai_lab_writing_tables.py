"""dabai 实验书架写作期产物表：预警 / 质检 / 记忆 / 线索。

dabai_pre_warn_records  写前导演单（每章最新一条）
dabai_quality_reports   章节质检报告（每章最新一条）
dabai_memories          复盘记忆条目（章级幂等）
dabai_clues             线索/伏笔台账（open/resolved/dropped）

Revision ID: f3a4b5c6d7e9
Revises: e2f3a4b5c6d7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "f3a4b5c6d7e9"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None

_TABLES = (
    "dabai_pre_warn_records",
    "dabai_quality_reports",
    "dabai_memories",
    "dabai_clues",
)


def _pid_fk() -> sa.Column:
    return sa.Column(
        "project_id", UUID(as_uuid=True),
        sa.ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )


def _cid_fk() -> sa.Column:
    return sa.Column(
        "chapter_id", UUID(as_uuid=True),
        sa.ForeignKey("dabai_chapter_outlines.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )


def upgrade() -> None:
    inspector = inspect(op.get_bind())

    if not inspector.has_table("dabai_pre_warn_records"):
        op.create_table(
            "dabai_pre_warn_records",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            _pid_fk(), _cid_fk(),
            sa.Column("chapter_number", sa.Integer()),
            sa.Column("version", sa.String(40)),
            sa.Column("result", sa.JSON(), server_default="{}"),
            sa.Column("brief", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not inspector.has_table("dabai_quality_reports"):
        op.create_table(
            "dabai_quality_reports",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            _pid_fk(), _cid_fk(),
            sa.Column("chapter_number", sa.Integer()),
            sa.Column("version", sa.String(40)),
            sa.Column("status", sa.String(20)),
            sa.Column("overall_score", sa.Integer()),
            sa.Column("report", sa.JSON(), server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not inspector.has_table("dabai_memories"):
        op.create_table(
            "dabai_memories",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            _pid_fk(), _cid_fk(),
            sa.Column("chapter_number", sa.Integer(), index=True),
            sa.Column("mem_type", sa.String(20), server_default="event"),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("importance", sa.Integer(), server_default="3"),
            sa.Column("tags", sa.JSON(), server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not inspector.has_table("dabai_clues"):
        op.create_table(
            "dabai_clues",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            _pid_fk(),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("clue_type", sa.String(20), server_default="hook"),
            sa.Column("description", sa.Text()),
            sa.Column("chapter_planted", sa.Integer()),
            sa.Column("chapter_resolved", sa.Integer()),
            sa.Column("status", sa.String(20), server_default="open"),
            sa.Column("source", sa.String(20), server_default="debrief"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    for table in reversed(_TABLES):
        if inspector.has_table(table):
            op.drop_table(table)
