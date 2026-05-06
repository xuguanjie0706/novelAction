"""characters.speech_kit JSON (语风指纹结构化字段)

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
"""

from __future__ import annotations

from alembic import op

revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE characters ADD COLUMN IF NOT EXISTS speech_kit JSON")


def downgrade() -> None:
    op.execute("ALTER TABLE characters DROP COLUMN IF EXISTS speech_kit")
