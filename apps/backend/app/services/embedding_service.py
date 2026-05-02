"""
Embedding Service — 异步向量化 + pgvector 语义检索

职责：
  1. embed_texts()   — 调用 Ollama / OpenAI 兼容 /v1/embeddings，返回向量列表
  2. embed_chunk()   — 单条 MemoryChunk 写入向量（后台 fire-and-forget）
  3. embed_chunks_bulk() — Bootstrap / 批量补跑时使用
  4. semantic_search() — 用 pgvector <=> 余弦距离召回最相关记忆

设计原则：
  - 不阻塞主流程：embed_chunk() 通过 asyncio.create_task 异步触发
  - 向量生成失败只记 warning，不抛异常（记忆保存先行，向量是增强）
  - 维度由 settings.EMBEDDING_DIM 统一管控，不硬编码
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 底层：调用 /v1/embeddings 端点
# ---------------------------------------------------------------------------

async def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    批量向量化。
    返回与 texts 等长的向量列表；任何单条失败会整批抛出异常，由上层决策。
    """
    if not texts:
        return []

    payload = {
        "model": settings.EMBEDDING_MODEL,
        "input": texts,
    }
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(
        base_url=settings.LLM_BASE_URL,
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0),
    ) as client:
        resp = await client.post("/embeddings", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    # OpenAI 兼容格式：{"data": [{"embedding": [...], "index": 0}, ...]}
    ordered = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in ordered]


# ---------------------------------------------------------------------------
# 单条写入（fire-and-forget 用）
# ---------------------------------------------------------------------------

async def _do_embed_chunk(chunk_id: UUID, text: str, db_factory) -> None:
    """
    实际执行向量化并写回 DB。
    由 embed_chunk_async() 包一层 try/except 调用。
    """
    try:
        from pgvector.sqlalchemy import Vector  # 若未安装则直接 skip
    except ImportError:
        logger.debug("pgvector not installed, skipping embedding for chunk %s", chunk_id)
        return

    try:
        vectors = await embed_texts([text])
        if not vectors:
            return
        vec = vectors[0]

        # 用独立 session，避免和主请求 session 竞争
        with db_factory() as db:
            from app.models.memory import MemoryChunk  # 延迟导入，避免循环
            chunk = db.query(MemoryChunk).filter(MemoryChunk.id == chunk_id).first()
            if chunk is None:
                return
            chunk.embedding = vec
            db.commit()
            logger.debug("Embedded memory chunk %s (%d dims)", chunk_id, len(vec))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to embed memory chunk %s: %s", chunk_id, exc)


def embed_chunk_async(chunk_id: UUID, text: str, db_factory) -> None:
    """
    非阻塞触发：在当前事件循环上创建后台任务。
    调用方法：embed_chunk_async(chunk.id, chunk.content, get_db_factory())
    """
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_do_embed_chunk(chunk_id, text, db_factory))
    except RuntimeError:
        # 非异步上下文（不太可能，防御性兜底）
        logger.warning("No running event loop, skipping embedding for chunk %s", chunk_id)


# ---------------------------------------------------------------------------
# 批量补跑（Bootstrap / 运维工具用）
# ---------------------------------------------------------------------------

async def embed_chunks_bulk(
    chunk_ids_texts: List[tuple[UUID, str]],
    db_factory,
    batch_size: int = 20,
) -> int:
    """
    批量补全 embedding，返回成功写入数量。
    chunk_ids_texts: [(chunk_id, text), ...]
    """
    try:
        from pgvector.sqlalchemy import Vector  # noqa: F401
    except ImportError:
        logger.warning("pgvector not installed, bulk embedding skipped")
        return 0

    success = 0
    for i in range(0, len(chunk_ids_texts), batch_size):
        batch = chunk_ids_texts[i : i + batch_size]
        texts = [t for _, t in batch]
        try:
            vectors = await embed_texts(texts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Batch embedding failed (batch %d): %s", i // batch_size, exc)
            continue

        with db_factory() as db:
            from app.models.memory import MemoryChunk
            for (cid, _), vec in zip(batch, vectors):
                chunk = db.query(MemoryChunk).filter(MemoryChunk.id == cid).first()
                if chunk:
                    chunk.embedding = vec
                    success += 1
            db.commit()

    return success


# ---------------------------------------------------------------------------
# 语义检索
# ---------------------------------------------------------------------------

async def semantic_search(
    db: Session,
    project_id: str | UUID,
    query: str,
    top_k: int = 10,
    memory_types: Optional[List[str]] = None,
    max_chapter: Optional[int] = None,
) -> list:
    """
    使用 pgvector 余弦距离召回最相关记忆条目。

    返回 MemoryChunk ORM 对象列表（已按相关度降序排列）。
    若 pgvector 不可用或向量化失败，则回退到时间序最新 top_k 条。

    Args:
        db: SQLAlchemy session
        project_id: 项目 UUID
        query: 查询文本（如章节摘要或质检问题）
        top_k: 最多返回条数
        memory_types: 筛选记忆类型，None 表示全部
        max_chapter: 只检索该章节编号及之前的记忆（防止未来伏笔泄漏）
    """
    from app.models.memory import MemoryChunk, HAS_PGVECTOR
    from sqlalchemy import text as sa_text

    def _fallback_query() -> list:
        """时间序兜底：最新 top_k 条（降序）。"""
        q = db.query(MemoryChunk).filter(MemoryChunk.project_id == str(project_id))
        if memory_types:
            q = q.filter(MemoryChunk.memory_type.in_(memory_types))
        if max_chapter is not None:
            q = q.filter(
                (MemoryChunk.chapter_number == None)  # noqa: E711
                | (MemoryChunk.chapter_number <= max_chapter)
            )
        return q.order_by(MemoryChunk.created_at.desc()).limit(top_k).all()

    if not HAS_PGVECTOR:
        return _fallback_query()

    try:
        vectors = await embed_texts([query])
        if not vectors:
            return _fallback_query()
        query_vec = vectors[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_search embed failed: %s — falling back to recency", exc)
        return _fallback_query()

    try:
        # 用 SQLAlchemy text() 直接写 pgvector 运算符（ORM 层暂无原生支持）
        type_filter = ""
        if memory_types:
            types_sql = ", ".join(f"'{t}'" for t in memory_types)
            type_filter = f"AND memory_type IN ({types_sql})"

        chapter_filter = ""
        if max_chapter is not None:
            chapter_filter = f"AND (chapter_number IS NULL OR chapter_number <= {int(max_chapter)})"

        vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"
        sql = sa_text(f"""
            SELECT id
            FROM memory_chunks
            WHERE project_id = :project_id
              AND embedding IS NOT NULL
              {type_filter}
              {chapter_filter}
            ORDER BY embedding <=> :query_vec::vector
            LIMIT :top_k
        """)
        rows = db.execute(
            sql,
            {"project_id": str(project_id), "query_vec": vec_str, "top_k": top_k},
        ).fetchall()

        if not rows:
            return _fallback_query()

        ids = [r[0] for r in rows]
        # 保持相关度顺序
        chunks_map = {
            c.id: c
            for c in db.query(MemoryChunk).filter(MemoryChunk.id.in_(ids)).all()
        }
        return [chunks_map[cid] for cid in ids if cid in chunks_map]

    except Exception as exc:  # noqa: BLE001
        logger.warning("semantic_search pgvector query failed: %s — falling back to recency", exc)
        return _fallback_query()
