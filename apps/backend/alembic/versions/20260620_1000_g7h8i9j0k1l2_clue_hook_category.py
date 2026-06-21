"""dabai_clues 加 hook_category 列（13式钩子分类）。

Revision ID: g7h8i9j0k1l2
Revises: c2d3e4f5a6b7
Create Date: 2026-06-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "g7h8i9j0k1l2"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "dabai_clues",
        sa.Column("hook_category", sa.String(30), nullable=True),
    )


def downgrade():
    op.drop_column("dabai_clues", "hook_category")
