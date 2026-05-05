from datetime import datetime
from typing import Literal, Optional
import uuid

from pydantic import BaseModel, Field


QualityDebtStatus = Literal["pending", "resolved", "dismissed"]


class QualityDebtUpdate(BaseModel):
    status: Optional[QualityDebtStatus] = None
    suggested_fix: Optional[str] = Field(default=None, max_length=2000)
    author_notes: Optional[str] = Field(default=None, max_length=4000)


class QualityDebtOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    chapter_id: Optional[uuid.UUID] = None
    source_chapter_number: int
    issue_type: str
    severity: str
    status: QualityDebtStatus
    summary: str
    suggested_fix: Optional[str] = None
    author_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
