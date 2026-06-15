"""dabai_memories 增加 pgvector embedding 列 + HNSW 余弦索引（实验书架语义召回）

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3

变更：
1. dabai_memories.embedding：vector(EMBEDDING_DIM)（仅当 pgvector 扩展已安装时）
2. 建 HNSW 余弦距离索引 idx_dabai_memories_embedding_cosine

背景：
  实验书架（dabai_* 表）原本无语义检索，写章记忆召回只走 近期窗口 + 重要度兜底，
  老的低重要度事实会掉出窗口且无法按相关度召回（长篇衔接断层主因之一）。
  本 migration 对齐精品文 memory_chunks，给 dabai_memories 加同维度向量列。

注意：
  - 维度取自 settings.EMBEDDING_DIM（默认 1024 / BAAI/bge-m3）；换模型需同步改 .env。
  - 无 pgvector 扩展的部署自动跳过（DO 块内判断 pg_extension），不阻断 upgrade。
  - 新列初始为 NULL；存量记忆补跑：python verify_pgvector.py --reembed-dabai（见脚本）。
"""

from __future__ import annotations

from alembic import op

revision = "f9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None

# 与 settings.EMBEDDING_DIM / b3c4d5e6f7a8 保持一致（BAAI/bge-m3 → 1024）
_DIM = 1024
_IDX = "idx_dabai_memories_embedding_cosine"


def upgrade() -> None:
    # 仅当 pgvector 扩展存在时才加向量列（dabai-only 部署可能没装）
    op.execute(
        "DO $$ BEGIN "
        "  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector') "
        "     AND NOT EXISTS ("
        "       SELECT 1 FROM information_schema.columns "
        "       WHERE table_name='dabai_memories' AND column_name='embedding'"
        "     ) THEN "
        f"    ALTER TABLE dabai_memories ADD COLUMN embedding vector({_DIM}); "
        f"    CREATE INDEX IF NOT EXISTS {_IDX} "
        "       ON dabai_memories USING hnsw (embedding vector_cosine_ops); "
        "  END IF; "
        "END $$"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_IDX}")
    op.execute(
        "DO $$ BEGIN "
        "  IF EXISTS ("
        "    SELECT 1 FROM information_schema.columns "
        "    WHERE table_name='dabai_memories' AND column_name='embedding'"
        "  ) THEN "
        "    ALTER TABLE dabai_memories DROP COLUMN embedding; "
        "  END IF; "
        "END $$"
    )
