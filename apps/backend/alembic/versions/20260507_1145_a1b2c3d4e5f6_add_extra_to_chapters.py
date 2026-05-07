"""Add extra JSON column to chapters for scene writing outline and other metadata

Revision ID: a1b2c3d4e5f6
Revises: f7a8b9c0d1e2
Create Date: 2026-05-07 11:45:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('chapters', sa.Column('extra', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'))


def downgrade() -> None:
    op.drop_column('chapters', 'extra')
