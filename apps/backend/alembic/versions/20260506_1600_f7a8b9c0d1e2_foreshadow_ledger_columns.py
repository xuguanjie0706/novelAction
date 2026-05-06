"""foreshadows: P2 ledger columns (type / distance / quality / volume_budget)

Revision ID: f7a8b9c0d1e2
Revises: f6a7b8c9d0e1
"""

from __future__ import annotations

from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS "
        "foreshadow_type VARCHAR(30) DEFAULT 'hook'"
    )
    op.execute(
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS "
        "min_distance INTEGER DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS "
        "max_distance INTEGER DEFAULT 15"
    )
    op.execute(
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS paid_off_quality INTEGER"
    )
    op.execute(
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS "
        "audience_aware INTEGER DEFAULT 3"
    )
    op.execute(
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS volume_budget JSON"
    )
    op.execute(
        "UPDATE foreshadows SET foreshadow_type = 'hook' WHERE foreshadow_type IS NULL"
    )
    op.execute(
        "UPDATE foreshadows SET min_distance = 1 WHERE min_distance IS NULL"
    )
    op.execute(
        "UPDATE foreshadows SET max_distance = 15 WHERE max_distance IS NULL"
    )
    op.execute(
        "UPDATE foreshadows SET audience_aware = 3 WHERE audience_aware IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE foreshadows DROP COLUMN IF EXISTS volume_budget")
    op.execute("ALTER TABLE foreshadows DROP COLUMN IF EXISTS audience_aware")
    op.execute("ALTER TABLE foreshadows DROP COLUMN IF EXISTS paid_off_quality")
    op.execute("ALTER TABLE foreshadows DROP COLUMN IF EXISTS max_distance")
    op.execute("ALTER TABLE foreshadows DROP COLUMN IF EXISTS min_distance")
    op.execute("ALTER TABLE foreshadows DROP COLUMN IF EXISTS foreshadow_type")
