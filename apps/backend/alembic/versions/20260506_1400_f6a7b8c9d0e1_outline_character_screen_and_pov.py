"""outline_nodes: character_screen_time + pov_character_id

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""

from __future__ import annotations

from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS character_screen_time JSON"
    )
    op.execute(
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS pov_character_id UUID"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE outline_nodes DROP COLUMN IF EXISTS pov_character_id"
    )
    op.execute(
        "ALTER TABLE outline_nodes DROP COLUMN IF EXISTS character_screen_time"
    )
