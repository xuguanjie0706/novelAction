from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
import uuid


class FactionCreate(BaseModel):
    name: str
    faction_type: str = "sect"
    alignment: str = "neutral"
    description: Optional[str] = None
    territory: Optional[str] = None
    strength_level: Optional[str] = None
    member_count: Optional[str] = None
    top_power: Optional[str] = None
    parent_faction_id: Optional[uuid.UUID] = None
    leader_character_id: Optional[uuid.UUID] = None
    key_members: List[Any] = []
    goals: Optional[str] = None
    resources: Optional[str] = None
    rivals: List[str] = []
    allies: List[str] = []
    attitude_to_protagonist: str = "neutral"
    history: Optional[str] = None
    secrets: Optional[str] = None
    sort_order: int = 0
    extra: dict = {}


class FactionUpdate(BaseModel):
    name: Optional[str] = None
    faction_type: Optional[str] = None
    alignment: Optional[str] = None
    description: Optional[str] = None
    territory: Optional[str] = None
    strength_level: Optional[str] = None
    member_count: Optional[str] = None
    top_power: Optional[str] = None
    parent_faction_id: Optional[uuid.UUID] = None
    leader_character_id: Optional[uuid.UUID] = None
    key_members: Optional[List[Any]] = None
    goals: Optional[str] = None
    resources: Optional[str] = None
    rivals: Optional[List[str]] = None
    allies: Optional[List[str]] = None
    attitude_to_protagonist: Optional[str] = None
    history: Optional[str] = None
    secrets: Optional[str] = None
    sort_order: Optional[int] = None
    extra: Optional[dict] = None


class FactionOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    parent_faction_id: Optional[uuid.UUID]
    name: str
    faction_type: str
    alignment: str
    description: Optional[str]
    territory: Optional[str]
    strength_level: Optional[str]
    member_count: Optional[str]
    top_power: Optional[str]
    leader_character_id: Optional[uuid.UUID]
    key_members: List[Any]
    goals: Optional[str]
    resources: Optional[str]
    rivals: List[str]
    allies: List[str]
    attitude_to_protagonist: str
    history: Optional[str]
    secrets: Optional[str]
    sort_order: int
    extra: dict
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
