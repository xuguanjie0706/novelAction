"""dabai 系统文台账增强 + 系统面板快照表。

dabai_assets 新增数值字段：
  grade              INTEGER NULL          品阶 0=凡品…4=传说
  base_stat          JSONB NULL            基础属性加成
  cooldown_chapters  INTEGER NULL          技能冷却章数
  last_used_chapter  INTEGER NULL          最近使用章号
  enhancement_level  INTEGER DEFAULT 0     强化层数

新表 dabai_panel_snapshots：
  每章复盘完成后存一条系统面板快照，
  作为下章写作的绝对数值基准（境界/战力/技能冷却/资产清单）。

Revision ID: b5c6d7e8f9a2
Revises: a4b5c6d7e8f1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "b5c6d7e8f9a2"
down_revision = "a4b5c6d7e8f1"
branch_labels = None
depends_on = None


def _col_exists(conn, table: str, col: str) -> bool:
    insp = inspect(conn)
    return col in {c["name"] for c in insp.get_columns(table)}


def _tbl_exists(conn, table: str) -> bool:
    insp = inspect(conn)
    return table in insp.get_table_names()


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. dabai_assets 新字段 ────────────────────────────────────────────────
    new_cols = [
        ("grade",             sa.Column("grade",             sa.Integer(), nullable=True)),
        ("base_stat",         sa.Column("base_stat",         JSONB(),      nullable=True)),
        ("cooldown_chapters", sa.Column("cooldown_chapters", sa.Integer(), nullable=True)),
        ("last_used_chapter", sa.Column("last_used_chapter", sa.Integer(), nullable=True)),
        ("enhancement_level", sa.Column("enhancement_level", sa.Integer(),
                                        nullable=False, server_default="0")),
    ]
    for col_name, col_def in new_cols:
        if not _col_exists(conn, "dabai_assets", col_name):
            op.add_column("dabai_assets", col_def)

    # ── 2. dabai_panel_snapshots 新表 ─────────────────────────────────────────
    if not _tbl_exists(conn, "dabai_panel_snapshots"):
        op.create_table(
            "dabai_panel_snapshots",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "project_id", UUID(as_uuid=True),
                sa.ForeignKey("dabai_projects.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column(
                "chapter_id", UUID(as_uuid=True),
                sa.ForeignKey("dabai_chapter_outlines.id", ondelete="CASCADE"),
                nullable=False, index=True,
            ),
            sa.Column("chapter_number", sa.Integer(), index=True),
            sa.Column("snapshot", JSONB(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()

    if _tbl_exists(conn, "dabai_panel_snapshots"):
        op.drop_table("dabai_panel_snapshots")

    for col_name in (
        "enhancement_level", "last_used_chapter",
        "cooldown_chapters", "base_stat", "grade",
    ):
        if _col_exists(conn, "dabai_assets", col_name):
            op.drop_column("dabai_assets", col_name)
