from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
import uuid


class StoryLineCreate(BaseModel):
    name: str
    line_type: str = "main"
    description: Optional[str] = None
    status: str = "planned"
    start_chapter: Optional[int] = None
    end_chapter: Optional[int] = None
    related_character_ids: List[str] = []
    key_beats: List[Any] = []
    core_conflict: Optional[str] = None
    resolution_direction: Optional[str] = None
    sort_order: int = 0
    extra: dict = {}


class StoryLineUpdate(BaseModel):
    name: Optional[str] = None
    line_type: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    start_chapter: Optional[int] = None
    end_chapter: Optional[int] = None
    related_character_ids: Optional[List[str]] = None
    key_beats: Optional[List[Any]] = None
    core_conflict: Optional[str] = None
    resolution_direction: Optional[str] = None
    sort_order: Optional[int] = None
    extra: Optional[dict] = None


class StoryLineOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    line_type: str
    description: Optional[str]
    status: str
    start_chapter: Optional[int]
    end_chapter: Optional[int]
    related_character_ids: List[str]
    key_beats: List[Any]
    core_conflict: Optional[str]
    resolution_direction: Optional[str]
    sort_order: int
    extra: dict
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
