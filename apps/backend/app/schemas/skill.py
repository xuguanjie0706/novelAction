from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
import uuid


class SkillCreate(BaseModel):
    name: str
    skill_type: str = "combat"
    grade: str = "earth"
    source: Optional[str] = None
    power_system_id: Optional[uuid.UUID] = None
    level_required: Optional[str] = None
    prerequisites: Optional[str] = None
    description: Optional[str] = None
    effects: Optional[str] = None
    limitations: Optional[str] = None
    mastery_stages: List[Any] = []
    mastered_by_character_ids: List[str] = []
    first_appearance_chapter: Optional[int] = None
    sort_order: int = 0
    extra: dict = {}


class SkillUpdate(BaseModel):
    name: Optional[str] = None
    skill_type: Optional[str] = None
    grade: Optional[str] = None
    source: Optional[str] = None
    power_system_id: Optional[uuid.UUID] = None
    level_required: Optional[str] = None
    prerequisites: Optional[str] = None
    description: Optional[str] = None
    effects: Optional[str] = None
    limitations: Optional[str] = None
    mastery_stages: Optional[List[Any]] = None
    mastered_by_character_ids: Optional[List[str]] = None
    first_appearance_chapter: Optional[int] = None
    sort_order: Optional[int] = None
    extra: Optional[dict] = None


class SkillOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    power_system_id: Optional[uuid.UUID]
    name: str
    skill_type: str
    grade: str
    source: Optional[str]
    level_required: Optional[str]
    prerequisites: Optional[str]
    description: Optional[str]
    effects: Optional[str]
    limitations: Optional[str]
    mastery_stages: List[Any]
    mastered_by_character_ids: List[str]
    first_appearance_chapter: Optional[int]
    sort_order: int
    extra: dict
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
