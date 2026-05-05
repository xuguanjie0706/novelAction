from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
import uuid


class ChangeItem(BaseModel):
    """单个字段的变更记录。"""
    field:  str            # 字段名，如 current_realm / current_status / skill_gained
    label:  str            # 中文展示名，如 境界 / 状态 / 习得技能
    before: Optional[Any] = None
    after:  Optional[Any] = None


class CharacterChangeLogOut(BaseModel):
    id:             uuid.UUID
    project_id:     uuid.UUID
    character_id:   uuid.UUID
    character_name: str

    chapter_id:     Optional[uuid.UUID] = None
    chapter_number: Optional[str]       = None
    chapter_title:  Optional[str]       = None

    source:  str                        # debrief / manual / bootstrap
    summary: Optional[str]             = None
    changes: List[ChangeItem]          = []

    created_at: datetime

    class Config:
        from_attributes = True
