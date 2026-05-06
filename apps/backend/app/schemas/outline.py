from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid


class OutlineNodeCreate(BaseModel):
    parent_id: Optional[uuid.UUID] = None
    node_type: str = "arc"   # volume / arc / chapter_plan
    title: str
    summary: Optional[str] = None
    hook: Optional[str] = None
    highlight: Optional[str] = None
    conflict: Optional[str] = None
    sort_order: int = 0
    expected_words: Optional[int] = None
    # 卷阶段：opening / rising / turning / dark_hour / climax / ending
    phase: Optional[str] = None
    # P2 三层调度字段（章节级）
    character_screen_time: Optional[dict] = None
    pov_character_id: Optional[uuid.UUID] = None
    extra: dict = Field(default_factory=dict)


class OutlineNodeUpdate(BaseModel):
    parent_id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    hook: Optional[str] = None
    highlight: Optional[str] = None
    conflict: Optional[str] = None
    sort_order: Optional[int] = None
    expected_words: Optional[int] = None
    reader_hook_score: Optional[int] = None
    phase: Optional[str] = None
    # P2 三层调度字段（章节级）
    character_screen_time: Optional[dict] = None
    pov_character_id: Optional[uuid.UUID] = None
    extra: Optional[dict] = None


class OutlineNodeOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    parent_id: Optional[uuid.UUID]
    node_type: str
    title: str
    summary: Optional[str]
    hook: Optional[str]
    highlight: Optional[str]
    conflict: Optional[str]
    sort_order: int
    expected_words: Optional[int]
    reader_hook_score: Optional[int]
    phase: Optional[str] = None
    # P2 三层调度字段（章节级）
    character_screen_time: Optional[dict] = None
    pov_character_id: Optional[uuid.UUID] = None
    extra: dict = Field(default_factory=dict)
    children: List["OutlineNodeOut"] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


OutlineNodeOut.model_rebuild()
