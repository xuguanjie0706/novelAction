"""outline_nodes.phase + projects.extra

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-05-05 12:00:00

迁移背景
========
对应"老编辑诊断"中第二周改动：

1. ``outline_nodes.phase``：卷阶段标记（opening/rising/turning/dark_hour/climax/ending），
   章节起草 prompt 按此切模板与采样档位（``llm_task_profiles.phase_to_draft_task``）。

2. ``projects.extra``：JSON 杂物字段。Step 0 立项会议（``GenerationService._gen_positioning``）
   将题材定位 / 受众画像 / 爽点节奏写到 ``extra.positioning``；写章节路径会读出该字段
   作为"作品基本面"塞入 system prompt。

幂等性
=====
开发期 main.py 的 ``_ensure_*_columns()`` 也会补这两列；本迁移使用 ``IF NOT EXISTS``
（PostgreSQL ≥ 9.6）保证多次执行不报错。
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # outline_nodes.phase
    op.execute(
        "ALTER TABLE outline_nodes ADD COLUMN IF NOT EXISTS phase VARCHAR(20)"
    )

    # projects.extra（JSON，未来作品级元设定都挂在这里）
    op.execute(
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS extra JSON"
    )


def downgrade() -> None:
    # 删字段是不可逆操作；若回滚需求出现，请评估是否应转移数据到独立表后再 DROP。
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS extra")
    op.execute("ALTER TABLE outline_nodes DROP COLUMN IF EXISTS phase")
