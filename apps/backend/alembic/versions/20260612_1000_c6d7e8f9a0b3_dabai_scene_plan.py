"""dabai 实验书架分场层 + 章纲场景载体。

dabai_chapter_outlines 新增：
  location  VARCHAR(120) NULL   场景载体（地点+事件，相邻章轮换防同质化）

新表 dabai_scene_plans：
  每章写前生成 2-4 场分场调度单（场景/在场/事件/台词弹药/感官锚点/字数预算），
  每章保留最新一条，正文按场推进——治「五拍一句话直接糊 2000 字」。

Revision ID: c6d7e8f9a0b3
Revises: b5c6d7e8f9a2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "c6d7e8f9a0b3"
down_revision = "b5c6d7e8f9a2"
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

    # ── 1. 章纲场景载体列 ─────────────────────────────────────────────────────
    if not _col_exists(conn, "dabai_chapter_outlines", "location"):
        op.add_column(
            "dabai_chapter_outlines",
            sa.Column("location", sa.String(120), nullable=True),
        )

    # ── 2. dabai_scene_plans 新表 ─────────────────────────────────────────────
    if not _tbl_exists(conn, "dabai_scene_plans"):
        op.create_table(
            "dabai_scene_plans",
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
            sa.Column("chapter_number", sa.Integer()),
            sa.Column("version", sa.String(40)),
            sa.Column("scenes", JSONB(), nullable=True),
            sa.Column("opening_line", sa.Text(), nullable=True),
            sa.Column("brief", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()

    if _tbl_exists(conn, "dabai_scene_plans"):
        op.drop_table("dabai_scene_plans")

    if _col_exists(conn, "dabai_chapter_outlines", "location"):
        op.drop_column("dabai_chapter_outlines", "location")
