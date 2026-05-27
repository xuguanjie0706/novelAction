from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
import uuid


class ProjectCreate(BaseModel):
    title: str
    genre: Optional[str] = None
    logline: Optional[str] = None
    premise: Optional[str] = None
    world_overview: Optional[str] = None
    story_core: Optional[dict] = {}
    target_words: Optional[int] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    genre: Optional[str] = None
    logline: Optional[str] = None
    premise: Optional[str] = None
    world_overview: Optional[str] = None
    story_core: Optional[dict] = None
    status: Optional[str] = None
    target_words: Optional[int] = None
    cover_url: Optional[str] = None
    extra: Optional[dict] = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    title: str
    genre: Optional[str]
    logline: Optional[str]
    premise: Optional[str]
    world_overview: Optional[str]
    story_core: Optional[dict]
    status: str
    target_words: Optional[int]
    cover_url: Optional[str]
    extra: Optional[dict] = None
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
