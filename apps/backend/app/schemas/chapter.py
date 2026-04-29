from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


class ChapterCreate(BaseModel):
    title: str
    outline_node_id: Optional[uuid.UUID] = None
    content: str = ""
    sort_order: int = 0


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    sort_order: Optional[int] = None
    status: Optional[str] = None


class ChapterOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    outline_node_id: Optional[uuid.UUID]
    title: str
    content: str
    word_count: int
    sort_order: int
    status: str
    last_quality_score: Optional[float]
    last_quality_report: Optional[Dict[str, Any]] = None
    quality_checked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ChapterVersionOut(BaseModel):
    id: uuid.UUID
    chapter_id: uuid.UUID
    word_count: Optional[int]
    note: Optional[str]
    is_auto: bool
    created_at: datetime

    class Config:
        from_attributes = True
