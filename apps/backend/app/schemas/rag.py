from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid

from pydantic import BaseModel, Field


class RagSearchHitOut(BaseModel):
    rank: int
    memory_id: uuid.UUID
    score: Optional[float] = None
    retrieval_source: Literal["semantic", "recency_anchor", "recency_fallback"]
    memory_type: str
    title: Optional[str] = None
    content: str
    content_preview: str
    chapter_number: Optional[int] = None
    tags: List[str] = []


class RagQueryRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(20, ge=1, le=100)
    max_chapter: Optional[int] = None
    types: Optional[str] = Field(
        None,
        description="逗号分隔 memory_type 过滤，如 event,character_state",
    )
    chapter_id: Optional[uuid.UUID] = None
    include_injected_summary: bool = True


class RagQueryResponse(BaseModel):
    log_id: uuid.UUID
    query: str
    params: Dict[str, Any]
    status: str
    duration_ms: int
    hits: List[RagSearchHitOut]
    memory_summary: str = ""
    answer_hint: str = ""


class RagRetrievalLogOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    chapter_id: Optional[uuid.UUID]
    source: str
    status: str
    duration_ms: int
    input_payload: Dict[str, Any]
    output_payload: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True
