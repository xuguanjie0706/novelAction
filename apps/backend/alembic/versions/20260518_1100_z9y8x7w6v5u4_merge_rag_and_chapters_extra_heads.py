"""合并双 head：rag_retrieval_logs + chapters.extra

Revision ID: z9y8x7w6v5u4
Revises: a1b2c3d4e5f7, h9i0j1k2l3m4
Create Date: 2026-05-18
"""
from typing import Sequence, Union

from alembic import op

revision: str = "z9y8x7w6v5u4"
down_revision: Union[str, tuple[str, ...], None] = ("a1b2c3d4e5f7", "h9i0j1k2l3m4")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
