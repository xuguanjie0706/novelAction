from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import datetime
import uuid


class ForeshadowBase(BaseModel):
    title: str
    description: Optional[str] = None
    code: Optional[str] = None

    laid_chapter_id: Optional[uuid.UUID] = None
    laid_chapter_number: Optional[int] = None

    resolved_chapter_id: Optional[uuid.UUID] = None
    resolved_chapter_number: Optional[int] = None
    planned_resolve_chapter: Optional[int] = None
    planned_action: str = Field(default="resolve", pattern="^(resolve|develop)$")

    status: str = Field(default="open", pattern="^(planned|open|resolved|dropped)$")
    priority: int = Field(default=3, ge=1, le=5)
    extra: Optional[dict[str, Any]] = None


class ForeshadowCreate(ForeshadowBase):
    pass


class ForeshadowUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    code: Optional[str] = None

    laid_chapter_id: Optional[uuid.UUID] = None
    laid_chapter_number: Optional[int] = None

    resolved_chapter_id: Optional[uuid.UUID] = None
    resolved_chapter_number: Optional[int] = None
    planned_resolve_chapter: Optional[int] = None
    planned_action: Optional[str] = Field(default=None, pattern="^(resolve|develop)$")

    status: Optional[str] = Field(default=None, pattern="^(planned|open|resolved|dropped)$")
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    extra: Optional[dict[str, Any]] = None


class ForeshadowOut(ForeshadowBase):
    id: uuid.UUID
    project_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
