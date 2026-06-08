"""大白文项目增对标分析字段：dabai_projects.benchmark（对标书+文笔/设定特征）。

Revision ID: dcab12345678
Revises: db8c2d3e4f50
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "dcab12345678"
down_revision = "db8c2d3e4f50"
branch_labels = None
depends_on = None


def _has_col(inspector, table: str, col: str) -> bool:
    return any(c["name"] == col for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table("dabai_projects"):
        return
    if not _has_col(inspector, "dabai_projects", "benchmark"):
        op.add_column("dabai_projects",
                      sa.Column("benchmark", postgresql.JSONB(astext_type=sa.Text()),
                                server_default="{}"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("dabai_projects") and _has_col(inspector, "dabai_projects", "benchmark"):
        op.drop_column("dabai_projects", "benchmark")
