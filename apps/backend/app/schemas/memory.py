from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid


class MemoryChunkCreate(BaseModel):
    chapter_id: Optional[uuid.UUID] = None
    memory_type: str = "event"
    title: Optional[str] = None
    content: str
    chapter_number: Optional[int] = None
    tags: List[str] = []


class MemoryChunkOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    chapter_id: Optional[uuid.UUID]
    memory_type: str
    title: Optional[str]
    content: str
    chapter_number: Optional[int]
    tags: List[str]
    created_at: datetime

    class Config:
        from_attributes = True
