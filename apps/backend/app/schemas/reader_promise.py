from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class ReaderPromiseBase(BaseModel):
    promise_text: str
    promise_type: str = Field(default="chapter_ending", pattern="^(chapter_ending|volume_ending|name_implication|chapter_comment_consensus|protagonist_claim)$")
    source_chapter_id: Optional[uuid.UUID] = None
    source_chapter_number: Optional[int] = None
    expected_chapter_window: Optional[int] = None
    expected_volume: Optional[int] = None
    priority: int = Field(default=3, ge=1, le=5)
    audience_aware: int = Field(default=3, ge=0, le=5)


class ReaderPromiseCreate(ReaderPromiseBase):
    pass


class ReaderPromiseUpdate(BaseModel):
    promise_text: Optional[str] = None
    promise_type: Optional[str] = Field(default=None, pattern="^(chapter_ending|volume_ending|name_implication|chapter_comment_consensus|protagonist_claim)$")
    expected_chapter_window: Optional[int] = None
    expected_volume: Optional[int] = None
    status: Optional[str] = Field(default=None, pattern="^(open|fulfilled|broken)$")
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    audience_aware: Optional[int] = Field(default=None, ge=0, le=5)


class ReaderPromiseOut(ReaderPromiseBase):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str = "open"
    fulfilled_chapter_id: Optional[uuid.UUID] = None
    fulfilled_chapter_number: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
