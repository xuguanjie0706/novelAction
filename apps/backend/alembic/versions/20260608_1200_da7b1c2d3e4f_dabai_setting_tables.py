"""大白文设定拆独立表：dabai_factions / dabai_characters / dabai_storylines；
并从 dabai_projects 移除 factions / characters / storylines 三个 JSON 列。

Revision ID: da7b1c2d3e4f
Revises: d5e6f7a8b9c0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "da7b1c2d3e4f"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def _has_col(inspector, table: str, col: str) -> bool:
    return any(c["name"] == col for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("dabai_factions"):
        op.create_table(
            "dabai_factions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("project_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("dabai_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("stance", sa.String(length=40), nullable=True),
            sa.Column("role", sa.Text(), nullable=True),
            sa.Column("power_tier", sa.String(length=100), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), server_default="0"),
        )
        op.create_index("ix_dabai_factions_project_id", "dabai_factions", ["project_id"])

    if not inspector.has_table("dabai_characters"):
        op.create_table(
            "dabai_characters",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("project_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("dabai_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("role", sa.String(length=60), nullable=True),
            sa.Column("tier", sa.String(length=20), nullable=True),
            sa.Column("start_realm", sa.String(length=60), nullable=True),
            sa.Column("persona", sa.Text(), nullable=True),
            sa.Column("function", sa.Text(), nullable=True),
            sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), server_default="{}"),
            sa.Column("sort_order", sa.Integer(), server_default="0"),
        )
        op.create_index("ix_dabai_characters_project_id", "dabai_characters", ["project_id"])

    if not inspector.has_table("dabai_storylines"):
        op.create_table(
            "dabai_storylines",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("project_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("dabai_projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("type", sa.String(length=30), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), server_default="0"),
        )
        op.create_index("ix_dabai_storylines_project_id", "dabai_storylines", ["project_id"])

    # 移除 dabai_projects 上的 JSON 列（已迁到独立表）
    for col in ("factions", "characters", "storylines"):
        if _has_col(inspector, "dabai_projects", col):
            op.drop_column("dabai_projects", col)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    # 回填 JSON 列
    for col in ("factions", "characters", "storylines"):
        if not _has_col(inspector, "dabai_projects", col):
            op.add_column("dabai_projects",
                          sa.Column(col, postgresql.JSONB(astext_type=sa.Text()), server_default="[]"))
    for tbl in ("dabai_storylines", "dabai_characters", "dabai_factions"):
        if inspector.has_table(tbl):
            op.drop_index(f"ix_{tbl}_project_id", table_name=tbl)
            op.drop_table(tbl)
