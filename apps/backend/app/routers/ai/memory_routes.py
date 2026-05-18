from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Chapter, MemoryChunk
from app.models.rag_retrieval_log import RagRetrievalLog
from app.schemas import MemoryChunkOut
from app.schemas.rag import RagQueryRequest, RagQueryResponse, RagRetrievalLogOut
from app.services.ai_service import AIService
from app.services.embedding_service import embed_chunk_async, semantic_search
from app.services.rag_retrieval_service import run_rag_query
from app.utils.chapter_numbering import display_chapter_number

router = APIRouter()


@router.post("/extract-memory", response_model=List[MemoryChunkOut])
async def extract_memory(
    project_id: str,
    chapter_id: str,
    model_profile: Literal["local", "gemini"] = "local",
    llm_provider_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    chapter_no = display_chapter_number(chapter.title, chapter.sort_order)
    svc = AIService(
        "gemini" if model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=llm_provider_id,
    )
    extracted = await svc.extract_memory(
        chapter_content=chapter.content,
        chapter_title=chapter.title,
        chapter_number=chapter_no,
    )

    results = []
    for item in extracted:
        chunk = MemoryChunk(
            project_id=project_id,
            chapter_id=chapter_id,
            chapter_number=chapter_no,
            **item
        )
        db.add(chunk)
        results.append(chunk)
    db.commit()
    for r in results:
        db.refresh(r)

    for r in results:
        embed_text = f"{r.title or ''}\n{r.content}".strip()
        embed_chunk_async(r.id, embed_text, SessionLocal)

    return results


@router.post("/memory/rag-query", response_model=RagQueryResponse)
async def rag_query_memory(
    project_id: str,
    req: RagQueryRequest,
    db: Session = Depends(get_db),
):
    """
    结构化 RAG 查询：自然语言问题 → 语义命中列表 + 注入摘要 + 可读 answer_hint。

    示例：「反派1号起了没」「反派1号怎么死的」
    """
    if req.chapter_id:
        ch = db.query(Chapter).filter(
            Chapter.id == req.chapter_id,
            Chapter.project_id == project_id,
        ).first()
        if not ch:
            raise HTTPException(404, "Chapter not found")
    memory_types = [t.strip() for t in req.types.split(",")] if req.types else None
    return await run_rag_query(
        db,
        project_id=project_id,
        query=req.q,
        top_k=req.top_k,
        max_chapter=req.max_chapter,
        memory_types=memory_types,
        chapter_id=req.chapter_id,
        include_injected_summary=req.include_injected_summary,
        source="rag_query",
    )


@router.get("/memory/rag-logs", response_model=List[RagRetrievalLogOut])
def list_rag_logs(
    project_id: str,
    chapter_id: Optional[UUID] = None,
    source: Optional[str] = Query(
        None,
        description="draft_context | pre_write_warning | suggest | rag_query",
    ),
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """查询项目 RAG 检索日志（写章 / 手动查询）。"""
    q = db.query(RagRetrievalLog).filter(RagRetrievalLog.project_id == project_id)
    if chapter_id is not None:
        q = q.filter(RagRetrievalLog.chapter_id == str(chapter_id))
    if source:
        q = q.filter(RagRetrievalLog.source == source)
    return q.order_by(RagRetrievalLog.created_at.desc()).limit(limit).all()


@router.get("/memory/rag-logs/{log_id}", response_model=RagRetrievalLogOut)
def get_rag_log(
    project_id: str,
    log_id: UUID,
    db: Session = Depends(get_db),
):
    row = (
        db.query(RagRetrievalLog)
        .filter(RagRetrievalLog.project_id == project_id, RagRetrievalLog.id == log_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "RAG log not found")
    return row


@router.get("/memory/search", response_model=List[MemoryChunkOut])
async def search_memory(
    project_id: str,
    q: str,
    top_k: int = 20,
    types: Optional[str] = None,
    max_chapter: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    语义记忆检索端点。

    使用 pgvector 余弦距离检索与 q 最相关的记忆条目；
    pgvector 不可用时自动降级为时序排列。

    Args:
        q: 查询文本，例如「青玄剑」「主角突破金丹期」「叛徒身份」
        top_k: 返回条数（默认 20，上限 100）
        types: 逗号分隔的 memory_type 过滤，如 ``foreshadow,event``；
               不传则不过滤类型
        max_chapter: 只检索该章节编号及之前的记忆，防止泄漏未发生的剧情
    """
    if not q or not q.strip():
        raise HTTPException(400, "q 不能为空")
    top_k = max(1, min(top_k, 100))
    memory_types = [t.strip() for t in types.split(",")] if types else None

    results = await semantic_search(
        db,
        project_id,
        q.strip(),
        top_k=top_k,
        memory_types=memory_types,
        max_chapter=max_chapter,
    )
    return results


@router.post("/memory/reembed")
async def reembed_memory(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    对 embedding 为 NULL 的 MemoryChunk 批量重新触发向量化（fire-and-forget）。

    用途：首次部署 pgvector 或 Embedding 服务重启后，对存量数据补跑 embedding，
    使语义检索（RAG）能召回所有历史记忆片段。

    Returns:
        queued: 已入队向量化的条目数
        skipped: embedding 已存在、无需补跑的条目数
    """
    # 用原生 SQL 过滤 NULL embedding，规避 pgvector 条件导入时 Column 可能未挂载的问题
    rows = db.execute(
        text(
            "SELECT id, title, content FROM memory_chunks "
            "WHERE project_id = :pid AND embedding IS NULL"
        ),
        {"pid": str(project_id)},
    ).fetchall()

    total = db.execute(
        text("SELECT COUNT(*) FROM memory_chunks WHERE project_id = :pid"),
        {"pid": str(project_id)},
    ).scalar()

    for row in rows:
        embed_text = f"{row.title or ''}\n{row.content or ''}".strip()
        if embed_text:
            embed_chunk_async(UUID(str(row.id)), embed_text, SessionLocal)

    queued = len(rows)
    skipped = (total or 0) - queued
    return {"queued": queued, "skipped": skipped, "total": total or 0}


@router.get("/memory", response_model=List[MemoryChunkOut])
def list_memory(
    project_id: str,
    memory_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = (
        db.query(MemoryChunk)
        .outerjoin(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(MemoryChunk.project_id == project_id)
    )
    if memory_type:
        q = q.filter(MemoryChunk.memory_type == memory_type)
    return q.order_by(
        func.coalesce(Chapter.sort_order, MemoryChunk.chapter_number, 0).asc(),
        MemoryChunk.created_at,
    ).all()
