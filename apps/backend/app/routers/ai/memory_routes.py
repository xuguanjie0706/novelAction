from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Chapter, MemoryChunk
from app.schemas import MemoryChunkOut
from app.services.ai_service import AIService
from app.services.embedding_service import embed_chunk_async
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
