from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Chapter, MemoryChunk
from app.schemas import MemoryChunkOut
from app.services.ai_service import AIService
from app.services.embedding_service import embed_chunk_async, semantic_search
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
