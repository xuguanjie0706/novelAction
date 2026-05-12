"""pgvector 扩展 + memory_chunks.embedding 列 + HNSW 索引

Revision ID: e3f4a5b6c7d8
Revises: b2c3d4e5f607

变更：
1. 启用 pgvector 扩展（CREATE EXTENSION IF NOT EXISTS vector）
2. memory_chunks 表新增 embedding vector(768) 列（nullable，初始均为 NULL）
3. 建立 HNSW 近似最近邻索引（vector_cosine_ops），加速语义检索

注意：
- 扩展启用需要 PostgreSQL superuser 或 rds_superuser 权限；
  若权限不足，upgrade 会抛出 ProgrammingError，需 DBA 手动执行后再重跑。
- HNSW 需要服务端 pgvector ≥ 0.5；若版本过低会 fallback 到启动时的
  _ensure_memory_embedding_column 钩子（会改用 ivfflat 或顺序扫描）。
- downgrade 只删索引和列，不 DROP EXTENSION（其他表可能依赖）。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e3f4a5b6c7d8"
down_revision = "b2c3d4e5f607"
branch_labels = None
depends_on = None

# 目标向量维度，与 settings.EMBEDDING_DIM 保持一致
EMBEDDING_DIM = 768


def upgrade() -> None:
    # ── 1. 启用 pgvector 扩展 ────────────────────────────────────────────────
    # CREATE EXTENSION IF NOT EXISTS 是幂等的；已安装时无副作用。
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── 2. 新增 embedding 列 ─────────────────────────────────────────────────
    # IF NOT EXISTS 防止重复执行时报错（如已由启动钩子创建）。
    op.execute(
        f"ALTER TABLE memory_chunks "
        f"ADD COLUMN IF NOT EXISTS embedding vector({EMBEDDING_DIM})"
    )

    # ── 3. HNSW 索引（余弦距离） ──────────────────────────────────────────────
    # IF NOT EXISTS 需要 pgvector ≥ 0.5；旧版本报语法错误时钩子会兜底。
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_chunks_embedding_cosine "
        "ON memory_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    # 先删索引，再删列；不 DROP EXTENSION（可能有其他表依赖）
    op.execute(
        "DROP INDEX IF EXISTS idx_memory_chunks_embedding_cosine"
    )
    op.execute(
        "ALTER TABLE memory_chunks DROP COLUMN IF EXISTS embedding"
    )
