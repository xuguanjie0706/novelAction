"""
Scene Schema — 三层调度之分场结构
"""

from typing import Optional, List, Any
from uuid import UUID
from pydantic import BaseModel, Field


class SceneBase(BaseModel):
    order: int
    title: Optional[str] = None
    time: Optional[str] = None
    story_day: Optional[str] = None
    location_name: Optional[str] = None
    pov_character_id: Optional[UUID] = None
    characters_on_stage: List[UUID] = Field(default_factory=list)
    goal: Optional[str] = None
    conflict: Optional[str] = None
    turn: Optional[str] = None
    hook: Optional[str] = None
    hook_strength: int = 3
    word_budget: int = 400
    pacing: str = "mid"          # fast/mid/slow
    sensory_focus: str = "mixed"


class SceneCreate(SceneBase):
    outline_node_id: Optional[UUID] = None
    chapter_id: Optional[UUID] = None


class SceneUpdate(BaseModel):
    title: Optional[str] = None
    time: Optional[str] = None
    story_day: Optional[str] = None
    location_name: Optional[str] = None
    pov_character_id: Optional[UUID] = None
    characters_on_stage: Optional[List[UUID]] = None
    goal: Optional[str] = None
    conflict: Optional[str] = None
    turn: Optional[str] = None
    hook: Optional[str] = None
    hook_strength: Optional[int] = None
    word_budget: Optional[int] = None
    pacing: Optional[str] = None
    sensory_focus: Optional[str] = None
    status: Optional[str] = None
    content: Optional[str] = None
    extra: Optional[dict] = None


class SceneRead(SceneBase):
    id: UUID
    project_id: UUID
    chapter_id: Optional[UUID] = None
    outline_node_id: Optional[UUID] = None
    actual_word_count: int = 0
    status: str = "planned"
    content: Optional[str] = None
    extra: dict = Field(default_factory=dict)

    class Config:
        from_attributes = True


class ScenePlanRequest(BaseModel):
    """请求为某 OutlineNode / Chapter 生成分场计划"""
    outline_node_id: Optional[UUID] = None
    chapter_id: Optional[UUID] = None
    chapter_title: Optional[str] = None
    chapter_summary: Optional[str] = None
    genre: Optional[str] = None
    model_profile: str = "local"
    llm_provider_id: Optional[UUID] = None


class ScenePlanResponse(BaseModel):
    scenes: List[SceneBase]
    total_word_budget: int
    notes: Optional[str] = None
