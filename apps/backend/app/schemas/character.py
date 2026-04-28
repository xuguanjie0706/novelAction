from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid


class CharacterCreate(BaseModel):
    name: str
    role: str = "supporting"
    gender: Optional[str] = None
    age: Optional[str] = None
    faction: Optional[str] = None
    avatar_url: Optional[str] = None
    personality: Optional[str] = None
    background: Optional[str] = None
    motivation: Optional[str] = None
    arc: Optional[str] = None
    strengths: List[str] = []
    weaknesses: List[str] = []
    special_traits: List[str] = []
    extra: dict = {}


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    faction: Optional[str] = None
    avatar_url: Optional[str] = None
    personality: Optional[str] = None
    background: Optional[str] = None
    motivation: Optional[str] = None
    arc: Optional[str] = None
    strengths: Optional[List[str]] = None
    weaknesses: Optional[List[str]] = None
    special_traits: Optional[List[str]] = None
    extra: Optional[dict] = None


class CharacterOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    role: str
    gender: Optional[str]
    age: Optional[str]
    faction: Optional[str]
    avatar_url: Optional[str]
    personality: Optional[str]
    background: Optional[str]
    motivation: Optional[str]
    arc: Optional[str]
    strengths: List[str]
    weaknesses: List[str]
    special_traits: List[str]
    extra: dict
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class RelationshipCreate(BaseModel):
    from_character_id: uuid.UUID
    to_character_id: uuid.UUID
    relation_type: str
    description: Optional[str] = None
    intensity: int = 5


class RelationshipOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    from_character_id: uuid.UUID
    to_character_id: uuid.UUID
    relation_type: str
    description: Optional[str]
    intensity: int

    class Config:
        from_attributes = True
