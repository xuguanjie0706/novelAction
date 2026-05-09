"""projects.user_id — 多用户隔离

Revision ID: b2c3d4e5f607
Revises: d1e2f3a4b5c6

变更：
1. projects 表新增 user_id（UUID, FK users.id, ON DELETE CASCADE，可空）
2. 历史项目（user_id IS NULL）一次性回填给最早注册的 active 用户
3. 创建索引 ix_projects_user_id 加速 list 过滤

注意：保留 nullable=True 以兼容上线前的遗留行；新建项目走业务层强制写入。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "b2c3d4e5f607"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 新增列（首次建表时也走 ALTER 路径以保持幂等）
    op.add_column(
        "projects",
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_user_id",
        "projects",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    # 2) 历史项目回填：归到最早注册的 active 用户（按需，单人/开发场景常用）
    op.execute(
        """
        UPDATE projects
           SET user_id = (
                 SELECT id FROM users
                  WHERE is_active = TRUE
                  ORDER BY created_at ASC
                  LIMIT 1
               )
         WHERE user_id IS NULL
           AND EXISTS (SELECT 1 FROM users WHERE is_active = TRUE)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_constraint("fk_projects_user_id", "projects", type_="foreignkey")
    op.drop_column("projects", "user_id")
