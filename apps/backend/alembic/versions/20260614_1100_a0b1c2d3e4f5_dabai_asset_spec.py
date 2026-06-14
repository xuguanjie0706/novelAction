"""dabai_assets 增加 spec JSON 列（写前导演单锁定的技能/道具详细规格）

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4

变更：
1. dabai_assets.spec：JSON nullable（用法/代价/进阶/限制）

背景：
  实验书架原本资产只有一段短 description，写前导演单不锁定技能/道具的详细
  用法·代价·进阶，分场与正文遇到关键功法/法宝只能即兴编（能力漂移主因）。
  本 migration 给 dabai_assets 加结构化 spec 列，由导演单（pre_warn）在功法/
  道具首次登场或被使用时一次性锁定，落库后供台账查询、后续章节沿用。

注意：
  - 新列初始为 NULL（旧资产无规格，导演单在被使用章节回填）。
  - 幂等：仅当列不存在时新增。
"""

from __future__ import annotations

from alembic import op

revision = "a0b1c2d3e4f5"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "  IF NOT EXISTS ("
        "    SELECT 1 FROM information_schema.columns "
        "    WHERE table_name='dabai_assets' AND column_name='spec'"
        "  ) THEN "
        "    ALTER TABLE dabai_assets ADD COLUMN spec JSON; "
        "  END IF; "
        "END $$"
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "  IF EXISTS ("
        "    SELECT 1 FROM information_schema.columns "
        "    WHERE table_name='dabai_assets' AND column_name='spec'"
        "  ) THEN "
        "    ALTER TABLE dabai_assets DROP COLUMN spec; "
        "  END IF; "
        "END $$"
    )
