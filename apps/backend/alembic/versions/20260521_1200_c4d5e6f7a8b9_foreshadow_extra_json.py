"""foreshadows: extra JSON（章纲同步 heat_log / 核心谜题元数据）

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
"""

from __future__ import annotations

from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE foreshadows ADD COLUMN IF NOT EXISTS extra JSON DEFAULT '{}'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE foreshadows DROP COLUMN IF EXISTS extra")
