from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
import uuid


class PowerSystemCreate(BaseModel):
    name: str
    system_type: str = "cultivation"
    description: Optional[str] = None
    levels: List[Any] = []
    cultivation_method: Optional[str] = None
    breakthrough_condition: Optional[str] = None
    special_rules: Optional[str] = None
    protagonist_current_rank: Optional[int] = None
    protagonist_end_rank: Optional[int] = None
    sort_order: int = 0
    extra: dict = {}


class PowerSystemUpdate(BaseModel):
    name: Optional[str] = None
    system_type: Optional[str] = None
    description: Optional[str] = None
    levels: Optional[List[Any]] = None
    cultivation_method: Optional[str] = None
    breakthrough_condition: Optional[str] = None
    special_rules: Optional[str] = None
    protagonist_current_rank: Optional[int] = None
    protagonist_end_rank: Optional[int] = None
    sort_order: Optional[int] = None
    extra: Optional[dict] = None


class PowerSystemOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    system_type: str
    description: Optional[str]
    levels: List[Any]
    cultivation_method: Optional[str]
    breakthrough_condition: Optional[str]
    special_rules: Optional[str]
    protagonist_current_rank: Optional[int]
    protagonist_end_rank: Optional[int]
    sort_order: int
    extra: dict
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
