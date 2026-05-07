"""Add version (optimistic lock) and deleted_at (soft delete) to chapters

Revision ID: f7a8b9c0d1e3
Revises: e6f7a8b9c0d1
Create Date: 2026-05-07 11:36:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f7a8b9c0d1e3'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chapters', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('chapters', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    # 移除 server_default，避免后续更新带默认值
    op.alter_column('chapters', 'version', server_default=None)


def downgrade() -> None:
    op.drop_column('chapters', 'deleted_at')
    op.drop_column('chapters', 'version')
