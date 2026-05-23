"""scene constraint fields: storyline_moves / faction_color / asset_spotlight /
   foreshadow_ops / debt_flags / structural_warnings / checklist_result

Revision ID: e2f3a4b5c6d8
Revises: d1e2f3a4b5c7
Create Date: 2026-05-23 12:00:00.000000

设计说明：
  为 Scene 表新增 7 个 nullable JSON 列，用于存储由 chapter_ingredients 服务
  计算的分场级约束信息（投料清单）。
  - storyline_moves: 故事线推进指令
  - faction_color: 势力/地盘着色
  - asset_spotlight: 技能/法宝聚光灯
  - foreshadow_ops: 伏笔操作指令
  - debt_flags: 债务标记
  - structural_warnings: 结构预警
  - checklist_result: 写后核验结果
  全部为 nullable，存量数据自动填 NULL，向后完全兼容。
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2f3a4b5c6d8'
down_revision = 'd1e2f3a4b5c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('scenes', sa.Column('storyline_moves', sa.JSON(), nullable=True))
    op.add_column('scenes', sa.Column('faction_color', sa.JSON(), nullable=True))
    op.add_column('scenes', sa.Column('asset_spotlight', sa.JSON(), nullable=True))
    op.add_column('scenes', sa.Column('foreshadow_ops', sa.JSON(), nullable=True))
    op.add_column('scenes', sa.Column('debt_flags', sa.JSON(), nullable=True))
    op.add_column('scenes', sa.Column('structural_warnings', sa.JSON(), nullable=True))
    op.add_column('scenes', sa.Column('checklist_result', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('scenes', 'checklist_result')
    op.drop_column('scenes', 'structural_warnings')
    op.drop_column('scenes', 'debt_flags')
    op.drop_column('scenes', 'foreshadow_ops')
    op.drop_column('scenes', 'asset_spotlight')
    op.drop_column('scenes', 'faction_color')
    op.drop_column('scenes', 'storyline_moves')
