from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
import uuid


class ItemCreate(BaseModel):
    name: str
    item_type: str = "artifact"
    rarity: str = "rare"
    description: Optional[str] = None
    origin: Optional[str] = None
    effects: Optional[str] = None
    limitations: Optional[str] = None
    current_owner_id: Optional[uuid.UUID] = None
    ownership_history: List[Any] = []
    story_significance: Optional[str] = None
    first_appearance_chapter: Optional[int] = None
    status: str = "intact"
    sort_order: int = 0
    extra: dict = {}


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    item_type: Optional[str] = None
    rarity: Optional[str] = None
    description: Optional[str] = None
    origin: Optional[str] = None
    effects: Optional[str] = None
    limitations: Optional[str] = None
    current_owner_id: Optional[uuid.UUID] = None
    ownership_history: Optional[List[Any]] = None
    story_significance: Optional[str] = None
    first_appearance_chapter: Optional[int] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None
    extra: Optional[dict] = None


class ItemOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    item_type: str
    rarity: str
    description: Optional[str]
    origin: Optional[str]
    effects: Optional[str]
    limitations: Optional[str]
    current_owner_id: Optional[uuid.UUID]
    ownership_history: List[Any]
    story_significance: Optional[str]
    first_appearance_chapter: Optional[int]
    status: str
    sort_order: int
    extra: dict
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
