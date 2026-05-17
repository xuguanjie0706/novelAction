"""
Embedding Service — 异步向量化 + pgvector 语义检索

职责：
  1. embed_texts()          — 调用 /v1/embeddings 返回向量
  2. embed_entity_async()   — 通用单条向量化（支持 MemoryChunk / Scene / Chapter）
  3. embed_chunks_bulk()    — 批量补全
  4. semantic_search()      — 余弦距离召回 MemoryChunk
  5. retrieve_relevant_memories_for_writing() — 写章节时自动拉取相关记忆片段

设计原则：
  - fire-and-forget，不阻塞主请求
  - pgvector 不可用时优雅降级
  - 失败只 warning，不抛异常

事件循环：
  - 在 async 路由中调用时，asyncio.get_event_loop() 可直接拿到运行中的 loop
  - 在 sync 路由（线程池）中调用时，需通过 set_main_event_loop() 预先保存主 loop，
    之后使用 run_coroutine_threadsafe() 跨线程提交任务
  - main.py startup 事件负责调用 set_main_event_loop()
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
# 主事件循环引用（由 main.py startup 写入，供 sync 路由线程使用）
# ---------------------------------------------------------------------------

_main_event_loop: asyncio.AbstractEventLoop | None = None


def set_main_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """
    在应用启动时由 main.py 调用，保存 uvicorn 主事件循环的引用。
    sync 路由（跑在线程池）调用 embed_*_async 时，会通过 run_coroutine_threadsafe
    将协程提交到此 loop，而不是在线程内自行创建新 loop。
    """
    global _main_event_loop
    _main_event_loop = loop


def _submit_to_event_loop(coro) -> None:
    """
    将协程安全地提交到 uvicorn 主事件循环。
    - 若当前线程已有运行中的 loop（async 路由），直接 create_task
    - 若在线程池中（sync 路由），通过 run_coroutine_threadsafe 跨线程提交
    - 两者都不可用时记 warning，跳过 embedding（不影响主流程）
    """
    try:
        # async 上下文：直接在当前 loop 创建 task
        running_loop = asyncio.get_running_loop()
        running_loop.create_task(coro)
        return
    except RuntimeError:
        pass  # 不在 async 上下文，走下面的跨线程路径

    if _main_event_loop is not None and _main_event_loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, _main_event_loop)
    else:
        logger.warning("No available event loop for embedding, task skipped")

# ---------------------------------------------------------------------------
# 底层：调用 /v1/embeddings 端点
# ---------------------------------------------------------------------------

async def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    批量向量化。
    返回与 texts 等长的向量列表；任何单条失败会整批抛出异常，由上层决策。

    端点优先级：
      EMBEDDING_BASE_URL（独立 embedding 服务）> LLM_BASE_URL（兜底，如 Ollama 同端口）
    对应 API key 同理，允许「远程 LLM + 本地 Ollama embedding」解耦部署。
    """
    if not texts:
        return []

    base_url = settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL
    api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY

    payload = {
        "model": settings.EMBEDDING_MODEL,
        "input": texts,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    logger.debug(
        "embed_texts: model=%s base_url=%s texts_count=%d",
        settings.EMBEDDING_MODEL, base_url, len(texts),
    )

    async with httpx.AsyncClient(
        base_url=base_url,
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
    非阻塞触发单条 MemoryChunk 向量化。
    兼容 async 路由（create_task）与 sync 路由（run_coroutine_threadsafe）。
    db_factory 应传入 SessionLocal（不是 get_db），内部直接实例化 session。
    """
    _submit_to_event_loop(_do_embed_chunk(chunk_id, text, db_factory))


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


# ---------------------------------------------------------------------------
# 通用实体向量化（支持 Scene / Chapter / MemoryChunk）
# ---------------------------------------------------------------------------

async def _do_embed_entity(entity_type: str, entity_id: UUID, text: str, db_factory) -> None:
    """后台执行向量化并写回对应表的 embedding 字段。"""
    try:
        from pgvector.sqlalchemy import Vector
    except ImportError:
        logger.debug("pgvector not installed, skip embedding for %s %s", entity_type, entity_id)
        return

    if not text or not text.strip():
        return

    try:
        vectors = await embed_texts([text[:4000]])  # 截断避免超长
        if not vectors:
            return
        vec = vectors[0]

        with db_factory() as db:
            if entity_type == "memory":
                from app.models.memory import MemoryChunk
                obj = db.query(MemoryChunk).filter(MemoryChunk.id == entity_id).first()
            elif entity_type == "scene":
                from app.models.scene import Scene
                obj = db.query(Scene).filter(Scene.id == entity_id).first()
            elif entity_type == "chapter":
                from app.models.chapter import Chapter
                obj = db.query(Chapter).filter(Chapter.id == entity_id).first()
            else:
                return

            if obj is None or not hasattr(obj, "embedding"):
                return
            obj.embedding = vec
            db.commit()
            logger.debug("Embedded %s %s (%d dims)", entity_type, entity_id, len(vec))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to embed %s %s: %s", entity_type, entity_id, exc)


def embed_entity_async(entity_type: str, entity_id: UUID, text: str, db_factory) -> None:
    """
    非阻塞触发实体向量化。entity_type: 'memory' | 'scene' | 'chapter'
    兼容 async 路由（create_task）与 sync 路由（run_coroutine_threadsafe）。
    db_factory 应传入 SessionLocal（不是 get_db），内部直接实例化 session。
    """
    _submit_to_event_loop(_do_embed_entity(entity_type, entity_id, text, db_factory))


# ---------------------------------------------------------------------------
# 写章节时自动检索相关记忆
# ---------------------------------------------------------------------------

async def retrieve_relevant_memories_for_writing(
    db: Session,
    project_id: str | UUID,
    chapter_content: str,
    top_k: int = 5,
    max_chapter: Optional[int] = None,
) -> list:
    """
    写章节 / 复盘时自动拉取最相关的记忆片段。
    取章节正文前 200 字作为 query，使用 semantic_search。
    """
    query = (chapter_content or "")[:200]
    if not query.strip():
        return []
    return await semantic_search(
        db,
        project_id,
        query,
        top_k=top_k,
        max_chapter=max_chapter,
    )
