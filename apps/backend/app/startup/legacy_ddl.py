"""
startup/legacy_ddl.py — 只保留「无法通过 Alembic migration 表达」的运行时 DDL。

背景
====
绝大多数 _ensure_xxx 启动 DDL 已被整合进
alembic/versions/20260520_1000_p1q2r3s4t5u6_consolidate_startup_ddl.py。

本模块仅保留两类例外：

1. **pgvector 维度感知操作**
   embedding 列的维度依赖运行时 ``settings.EMBEDDING_DIM``，
   且在维度不匹配时需要「删列重建」，这是破坏性操作，不适合放在 migration 里静态写死。

2. **数据迁移**
   ``_claim_orphan_projects``：把 user_id IS NULL 的历史项目归属到最早注册用户，
   结果取决于当前 users 表状态，也不适合静态 migration。

禁止事项
========
- 禁止在本模块新增 schema DDL（新字段请走 alembic revision）
- 禁止在本模块做复杂业务逻辑
"""
from __future__ import annotations

import logging

from sqlalchemy import text

log = logging.getLogger(__name__)


def _ensure_memory_embedding_column(engine) -> None:
    """
    运行时 pgvector 维度感知迁移：memory_chunks.embedding。

    - 启用 pgvector 扩展（若未安装则静默跳过，语义检索降级）
    - 若 embedding 列维度与 ``settings.EMBEDDING_DIM`` 不一致，删列重建
    - 无 embedding 列时以正确维度新建
    - 建立 HNSW 索引（已有则跳过）

    Args:
        engine: SQLAlchemy engine 实例（由 main.py 传入）。
    """
    from app.config import settings as app_settings

    target_dim = app_settings.EMBEDDING_DIM

    with engine.begin() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception:  # noqa: BLE001
            log.warning("pgvector 扩展不可用，语义检索将降级。")
            return

        row = conn.execute(text("""
            SELECT atttypmod
            FROM pg_attribute
            WHERE attrelid = 'memory_chunks'::regclass
              AND attname  = 'embedding'
              AND attnum   > 0
              AND NOT attisdropped
        """)).fetchone()

        if row is None:
            conn.execute(text(
                f"ALTER TABLE memory_chunks "
                f"ADD COLUMN IF NOT EXISTS embedding vector({target_dim})"
            ))
        else:
            type_row = conn.execute(text("""
                SELECT pg_catalog.format_type(atttypid, atttypmod)
                FROM pg_attribute
                WHERE attrelid = 'memory_chunks'::regclass
                  AND attname  = 'embedding'
                  AND attnum   > 0
                  AND NOT attisdropped
            """)).fetchone()
            col_type = type_row[0] if type_row else ""
            if f"vector({target_dim})" not in col_type:
                log.warning(
                    "memory_chunks.embedding 维度不匹配（当前 %s，目标 %d），"
                    "删列重建（历史向量清空）。",
                    col_type,
                    target_dim,
                )
                conn.execute(text("ALTER TABLE memory_chunks DROP COLUMN embedding"))
                conn.execute(text(
                    f"ALTER TABLE memory_chunks "
                    f"ADD COLUMN embedding vector({target_dim})"
                ))

        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_memory_chunks_embedding_cosine
                ON memory_chunks
                USING hnsw (embedding vector_cosine_ops)
            """))
        except Exception:  # noqa: BLE001
            log.info("HNSW 索引创建跳过（pgvector 版本可能不支持），语义检索降级。")


def _ensure_chapter_embedding_column(engine) -> None:
    """
    运行时 pgvector 维度感知迁移：chapters.embedding。

    与 memory_chunks 同逻辑，依赖 pgvector 扩展已被 _ensure_memory_embedding_column 启用。

    Args:
        engine: SQLAlchemy engine 实例。
    """
    from app.config import settings as app_settings

    target_dim = app_settings.EMBEDDING_DIM

    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT 1 FROM pg_extension WHERE extname = 'vector'
        """)).fetchone()
        if not row:
            return  # pgvector 未安装，跳过

        existing = conn.execute(text("""
            SELECT pg_catalog.format_type(atttypid, atttypmod)
            FROM pg_attribute
            WHERE attrelid = 'chapters'::regclass
              AND attname  = 'embedding'
              AND attnum   > 0
              AND NOT attisdropped
        """)).fetchone()

        if existing is None:
            conn.execute(text(
                f"ALTER TABLE chapters "
                f"ADD COLUMN IF NOT EXISTS embedding vector({target_dim})"
            ))
        elif f"vector({target_dim})" not in existing[0]:
            log.warning(
                "chapters.embedding 维度不匹配（当前 %s，目标 %d），删列重建。",
                existing[0],
                target_dim,
            )
            conn.execute(text("ALTER TABLE chapters DROP COLUMN embedding"))
            conn.execute(text(
                f"ALTER TABLE chapters ADD COLUMN embedding vector({target_dim})"
            ))


def _claim_orphan_projects(engine) -> None:
    """
    数据迁移（幂等）：将引入 user_id 之前创建的历史项目归属到最早注册的活跃用户。

    无活跃用户时不做动作；回填一次后后续 NULL 行为空，不再触发。

    Args:
        engine: SQLAlchemy engine 实例。
    """
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'users'"
        )).fetchone()
        if not row:
            return
        conn.execute(text("""
            UPDATE projects
               SET user_id = (
                     SELECT id FROM users
                      WHERE is_active = TRUE
                      ORDER BY created_at ASC
                      LIMIT 1
                   )
             WHERE user_id IS NULL
               AND EXISTS (SELECT 1 FROM users WHERE is_active = TRUE)
        """))


def run_startup_ddl(engine) -> None:
    """
    执行所有仅限运行时的 DDL 与数据修复。

    由 main.py 在 ``Base.metadata.create_all`` 之后、FastAPI app 实例化之前调用。
    所有操作均幂等，多次调用安全。

    Args:
        engine: SQLAlchemy engine 实例（来自 app.database）。
    """
    _ensure_memory_embedding_column(engine)
    _ensure_chapter_embedding_column(engine)
    _claim_orphan_projects(engine)
