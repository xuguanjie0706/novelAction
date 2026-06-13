"""大白文规划层扩列：项目/卷 extra + 势力场景池 + 故事线节点。

新步骤产物落库（持久化优先）：
  - dabai_projects.extra      反派阶梯 / 谜题排程 / 书名海选 / 节拍序列快照
  - dabai_factions.locations  势力驻地+周边场景池（章纲 location 轮换素材）
  - dabai_storylines.nodes    故事线关键节点（卷绑定）
  - dabai_storylines.bound_characters  线绑定人物
  - dabai_volumes.extra       卷级 boss / storyline_moves / mystery_moves

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None

_COLUMNS: list[tuple[str, str, sa.types.TypeEngine, str]] = [
    ("dabai_projects", "extra", sa.JSON(), "'{}'"),
    ("dabai_factions", "locations", sa.JSON(), "'[]'"),
    ("dabai_storylines", "nodes", sa.JSON(), "'[]'"),
    ("dabai_storylines", "bound_characters", sa.JSON(), "'[]'"),
    ("dabai_volumes", "extra", sa.JSON(), "'{}'"),
]


def _has_col(inspector, table: str, col: str) -> bool:
    return any(c["name"] == col for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table, col, typ, default in _COLUMNS:
        if inspector.has_table(table) and not _has_col(inspector, table, col):
            op.add_column(table, sa.Column(col, typ, nullable=True,
                                           server_default=sa.text(default)))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    for table, col, _typ, _default in reversed(_COLUMNS):
        if inspector.has_table(table) and _has_col(inspector, table, col):
            op.drop_column(table, col)
