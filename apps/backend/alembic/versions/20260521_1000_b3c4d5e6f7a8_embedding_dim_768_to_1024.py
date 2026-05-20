"""将 embedding 列维度从 vector(768) 升级到 vector(1024)

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7

变更：
1. memory_chunks.embedding：vector(768) → vector(1024)
2. chapters.embedding：vector(768) → vector(1024)（若存在）
3. 重建对应 HNSW 索引（余弦距离）

背景：
  原始 migration（e3f4a5b6c7d8）将维度硬编码为 768（nomic-embed-text）。
  现统一切换为 BAAI/bge-m3（1024 维），需同步修改 DB 列维度。

注意：
  - ALTER COLUMN TYPE 需要先删除依赖该列的索引，改完再重建。
  - 已有的 768 维向量全部清空（SET NULL）；切换后须重新触发 embedding
    补跑：cd apps/backend && python verify_pgvector.py --reembed
  - downgrade 将维度还原回 768，同样清空向量数据。
  - 同步修改 .env：EMBEDDING_MODEL=BAAI/bge-m3  EMBEDDING_DIM=1024
"""

from __future__ import annotations

from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None

_OLD_DIM = 768
_NEW_DIM = 1024

# HNSW 索引名（与原 migration 保持一致）
_MEM_IDX = "idx_memory_chunks_embedding_cosine"
_CH_IDX  = "idx_chapters_embedding_cosine"


def upgrade() -> None:
    # ── memory_chunks ────────────────────────────────────────────────────────
    op.execute(f"DROP INDEX IF EXISTS {_MEM_IDX}")
    # 先清空旧维度向量（维度不同无法 CAST），再改列类型
    op.execute("UPDATE memory_chunks SET embedding = NULL WHERE embedding IS NOT NULL")
    op.execute(
        f"ALTER TABLE memory_chunks "
        f"ALTER COLUMN embedding TYPE vector({_NEW_DIM}) "
        f"USING NULL"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_MEM_IDX} "
        f"ON memory_chunks USING hnsw (embedding vector_cosine_ops)"
    )

    # ── chapters（可选列，IF EXISTS 防止不存在时报错）──────────────────────
    op.execute(f"DROP INDEX IF EXISTS {_CH_IDX}")
    op.execute(
        "DO $$ BEGIN "
        "  IF EXISTS ("
        "    SELECT 1 FROM information_schema.columns "
        "    WHERE table_name='chapters' AND column_name='embedding'"
        "  ) THEN "
        f"   UPDATE chapters SET embedding = NULL WHERE embedding IS NOT NULL; "
        f"   ALTER TABLE chapters ALTER COLUMN embedding TYPE vector({_NEW_DIM}) USING NULL; "
        "  END IF; "
        "END $$"
    )
    # 仅当列存在时建索引
    op.execute(
        "DO $$ BEGIN "
        "  IF EXISTS ("
        "    SELECT 1 FROM information_schema.columns "
        "    WHERE table_name='chapters' AND column_name='embedding'"
        "  ) THEN "
        f"   CREATE INDEX IF NOT EXISTS {_CH_IDX} "
        f"   ON chapters USING hnsw (embedding vector_cosine_ops); "
        "  END IF; "
        "END $$"
    )


def downgrade() -> None:
    # ── memory_chunks ────────────────────────────────────────────────────────
    op.execute(f"DROP INDEX IF EXISTS {_MEM_IDX}")
    op.execute("UPDATE memory_chunks SET embedding = NULL WHERE embedding IS NOT NULL")
    op.execute(
        f"ALTER TABLE memory_chunks "
        f"ALTER COLUMN embedding TYPE vector({_OLD_DIM}) "
        f"USING NULL"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {_MEM_IDX} "
        f"ON memory_chunks USING hnsw (embedding vector_cosine_ops)"
    )

    # ── chapters ─────────────────────────────────────────────────────────────
    op.execute(f"DROP INDEX IF EXISTS {_CH_IDX}")
    op.execute(
        "DO $$ BEGIN "
        "  IF EXISTS ("
        "    SELECT 1 FROM information_schema.columns "
        "    WHERE table_name='chapters' AND column_name='embedding'"
        "  ) THEN "
        f"   UPDATE chapters SET embedding = NULL WHERE embedding IS NOT NULL; "
        f"   ALTER TABLE chapters ALTER COLUMN embedding TYPE vector({_OLD_DIM}) USING NULL; "
        "  END IF; "
        "END $$"
    )
    op.execute(
        "DO $$ BEGIN "
        "  IF EXISTS ("
        "    SELECT 1 FROM information_schema.columns "
        "    WHERE table_name='chapters' AND column_name='embedding'"
        "  ) THEN "
        f"   CREATE INDEX IF NOT EXISTS {_CH_IDX} "
        f"   ON chapters USING hnsw (embedding vector_cosine_ops); "
        "  END IF; "
        "END $$"
    )
