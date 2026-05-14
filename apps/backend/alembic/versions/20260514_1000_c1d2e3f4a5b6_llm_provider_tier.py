"""llm_providers 表增加 tier 计费档位字段

Revision ID: c1d2e3f4a5b6
Revises: g8h9i0j1k2l3
Create Date: 2026-05-14 10:00:00.000000

tier 取值：heavy / standard / light（默认 standard）。
由管理员在后台配置时显式指定，替代之前基于模型名关键词猜测档位的脆弱方案。
"""
from alembic import op
import sqlalchemy as sa

revision = "c1d2e3f4a5b6"
down_revision = "g8h9i0j1k2l3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_providers",
        sa.Column(
            "tier",
            sa.String(20),
            nullable=False,
            server_default="standard",
        ),
    )


def downgrade() -> None:
    op.drop_column("llm_providers", "tier")
