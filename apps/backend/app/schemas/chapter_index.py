from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid


class ChapterIndexBase(BaseModel):
    chapter_number: int
    story_day: Optional[str] = None
    core_events: List[dict | str] = Field(default_factory=list)
    first_appearances: List[dict] = Field(default_factory=list)
    actual_foreshadows_laid: List[dict] = Field(default_factory=list)
    actual_foreshadows_resolved: List[dict] = Field(default_factory=list)
    ending_hook: Optional[str] = None
    hook_strength: int = 1
    continuity_notes: List[dict | str] = Field(default_factory=list)


class ChapterIndexCreate(ChapterIndexBase):
    chapter_id: uuid.UUID


class ChapterIndexUpdate(BaseModel):
    story_day: Optional[str] = None
    core_events: Optional[List[dict | str]] = None
    first_appearances: Optional[List[dict]] = None
    actual_foreshadows_laid: Optional[List[dict]] = None
    actual_foreshadows_resolved: Optional[List[dict]] = None
    ending_hook: Optional[str] = None
    hook_strength: Optional[int] = None
    continuity_notes: Optional[List[dict | str]] = None


class ChapterIndexOut(ChapterIndexBase):
    id: uuid.UUID
    project_id: uuid.UUID
    chapter_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
