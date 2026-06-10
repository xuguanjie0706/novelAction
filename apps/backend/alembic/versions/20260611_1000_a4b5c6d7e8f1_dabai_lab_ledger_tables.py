"""dabai 实验书架双台账表：资产（功法/道具/金手指）+ 人物关系。

dabai_assets     资产台账（防能力与装备漂移；seed/debrief/manual）
dabai_relations  关系台账（主角视角态度轨迹，history 保留完整变化）

Revision ID: a4b5c6d7e8f1
Revises: f3a4b5c6d7e9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID

revision = "a4b5c6d7e8f1"
down_revision = "f3a4b5c6d7e9"
branch_labels = None
depends_on = None


def _pid_fk() -> sa.Column:
    return sa.Column(
        "project_id", UUID(as_uuid=True),
        sa.ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )


def upgrade() -> None:
    inspector = inspect(op.get_bind())

    if not inspector.has_table("dabai_assets"):
        op.create_table(
            "dabai_assets",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            _pid_fk(),
            sa.Column("kind", sa.String(20), server_default="item"),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("owner", sa.String(100)),
            sa.Column("description", sa.Text()),
            sa.Column("acquired_chapter", sa.Integer()),
            sa.Column("status", sa.String(20), server_default="active"),
            sa.Column("status_chapter", sa.Integer()),
            sa.Column("source", sa.String(20), server_default="debrief"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not inspector.has_table("dabai_relations"):
        op.create_table(
            "dabai_relations",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            _pid_fk(),
            sa.Column("from_name", sa.String(100), nullable=False),
            sa.Column("to_name", sa.String(100), nullable=False),
            sa.Column("attitude", sa.String(40)),
            sa.Column("note", sa.Text()),
            sa.Column("last_change_chapter", sa.Integer()),
            sa.Column("history", sa.JSON(), server_default="[]"),
            sa.Column("source", sa.String(20), server_default="debrief"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    for table in ("dabai_relations", "dabai_assets"):
        if inspector.has_table(table):
            op.drop_table(table)
