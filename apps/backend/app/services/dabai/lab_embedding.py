"""实验书架（dabai_memories）pgvector 语义召回 — 与精品文 embedding_service 对齐。

职责：
  1. ``embed_dabai_memories_async``：复盘落库后异步向量化新记忆（fire-and-forget）。
  2. ``semantic_search_dabai``：按查询语义召回最相关记忆（pgvector 余弦距离）。

降级：pgvector 未安装 / 向量化失败 / 查询异常时，全部返回空列表（调用方
回退到 实体召回 + 近期窗口 + 重要度兜底），不阻塞写章。
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.models.dabai_lab import HAS_PGVECTOR, DabaiMemory
from app.services.embedding_service import (
    _submit_to_event_loop,
    _validate_embedding_dims,
    _vector_to_pg_literal,
    embed_texts,
)

logger = logging.getLogger("dabai.lab_embedding")

# 不参与语义召回的类型（摘要是章级总览，单独走摘要链注入）
_SKIP_TYPES = {"summary"}


async def _do_embed_memories(mem_ids: list[str], db_factory) -> None:
    """后台批量向量化指定记忆条目，写回 dabai_memories.embedding。"""
    if not HAS_PGVECTOR or not mem_ids:
        return
    try:
        with db_factory() as db:
            rows = (
                db.query(DabaiMemory)
                .filter(DabaiMemory.id.in_([UUID(m) for m in mem_ids]))
                .all()
            )
            targets = [r for r in rows if (r.content or "").strip()]
            if not targets:
                return
            vectors = await embed_texts([r.content[:2000] for r in targets])
            if not vectors or len(vectors) != len(targets):
                return
            for row, vec in zip(targets, vectors):
                row.embedding = _validate_embedding_dims(vec, context=str(row.id))
            db.commit()
            logger.debug("Embedded %d dabai memories", len(targets))
    except Exception as exc:  # noqa: BLE001
        logger.warning("dabai memory embedding failed: %s", exc)


def embed_dabai_memories_async(rows: list[DabaiMemory], db_factory) -> None:
    """非阻塞触发记忆向量化。rows 为复盘刚落库的记忆（summary 跳过）。

    db_factory 应传入 SessionLocal（内部自行实例化 session，独立于请求 session）。
    """
    if not HAS_PGVECTOR:
        return
    mem_ids = [
        str(r.id) for r in rows
        if r.id and (r.mem_type or "") not in _SKIP_TYPES and (r.content or "").strip()
    ]
    if mem_ids:
        _submit_to_event_loop(_do_embed_memories(mem_ids, db_factory))


async def semantic_search_dabai(
    db: Session,
    project_id: str | UUID,
    query: str,
    *,
    top_k: int = 8,
    max_chapter: Optional[int] = None,
) -> list[DabaiMemory]:
    """pgvector 余弦距离召回最相关记忆（降序）。失败/不可用时返回 []。

    Args:
        max_chapter: 只召回 chapter_number < max_chapter 的记忆（避免泄露未来剧情）。
    """
    if not HAS_PGVECTOR or not (query or "").strip():
        return []
    try:
        vectors = await embed_texts([query[:2000]])
        if not vectors:
            return []
        vec_str = _vector_to_pg_literal(
            _validate_embedding_dims(vectors[0], context="dabai-query")
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("dabai semantic embed failed: %s", exc)
        return []

    try:
        where = [
            "project_id = :pid",
            "embedding IS NOT NULL",
            "mem_type <> 'summary'",
        ]
        params: dict = {"pid": str(project_id), "qv": vec_str, "k": top_k}
        if max_chapter is not None:
            where.append("(chapter_number IS NULL OR chapter_number < :maxc)")
            params["maxc"] = int(max_chapter)
        sql = sa_text(
            "SELECT id, (embedding <=> CAST(:qv AS vector)) AS dist "
            "FROM dabai_memories WHERE " + " AND ".join(where)
            + " ORDER BY dist ASC LIMIT :k"
        )
        hits = db.execute(sql, params).fetchall()
        if not hits:
            return []
        order = [h[0] for h in hits]
        rows = {
            r.id: r
            for r in db.query(DabaiMemory).filter(DabaiMemory.id.in_(order)).all()
        }
        return [rows[i] for i in order if i in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("dabai semantic query failed: %s", exc)
        return []
