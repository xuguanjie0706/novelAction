from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid


class WorldSettingCreate(BaseModel):
    title: str
    category_id: Optional[uuid.UUID] = None
    content: Optional[str] = None
    tags: List[str] = []
    extra: dict = {}


class WorldSettingUpdate(BaseModel):
    title: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    extra: Optional[dict] = None


class WorldSettingOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    category_id: Optional[uuid.UUID]
    title: str
    content: Optional[str]
    tags: List[str]
    extra: dict
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
