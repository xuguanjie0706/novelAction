from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
import uuid


class CharacterCreate(BaseModel):
    name: str
    alias: List[str] = []
    role: str = "supporting"
    # 叙事层级：core=核心长线 / arc=弧线支柱 / plot=剧情推手 / background=背景填充
    character_tier: str = "core"
    gender: Optional[str] = None
    age: Optional[str] = None
    avatar_url: Optional[str] = None

    # 归属
    faction: Optional[str] = None
    faction_id: Optional[uuid.UUID] = None
    faction_rank: Optional[str] = None
    birthplace: Optional[str] = None

    # 外貌
    appearance: Optional[str] = None
    clothing_style: Optional[str] = None

    # 能力与境界
    current_realm: Optional[str] = None
    power_system_id: Optional[uuid.UUID] = None
    realm_rank: Optional[int] = None

    # 性格
    personality: Optional[str] = None
    speech_style: Optional[str] = None
    speech_kit: Optional[dict] = None  # 结构化语风指纹
    values: Optional[str] = None

    # 背景
    background: Optional[str] = None
    secrets: Optional[str] = None
    trauma: Optional[str] = None

    # 动机与成长
    motivation: Optional[str] = None
    fear: Optional[str] = None
    arc: Optional[str] = None
    arc_stages: List[Any] = []

    # 能力标签
    strengths: List[str] = []
    weaknesses: List[str] = []
    special_traits: List[str] = []

    # 技能与道具
    known_skills: List[Any] = []
    owned_items: List[Any] = []

    # 当前状态
    current_status: str = "alive"
    current_location: Optional[str] = None

    # 备注
    author_notes: Optional[str] = None
    extra: dict = {}


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    alias: Optional[List[str]] = None
    role: Optional[str] = None
    character_tier: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    avatar_url: Optional[str] = None

    faction: Optional[str] = None
    faction_id: Optional[uuid.UUID] = None
    faction_rank: Optional[str] = None
    birthplace: Optional[str] = None

    appearance: Optional[str] = None
    clothing_style: Optional[str] = None

    current_realm: Optional[str] = None
    power_system_id: Optional[uuid.UUID] = None
    realm_rank: Optional[int] = None

    personality: Optional[str] = None
    speech_style: Optional[str] = None
    values: Optional[str] = None

    background: Optional[str] = None
    secrets: Optional[str] = None
    trauma: Optional[str] = None

    motivation: Optional[str] = None
    fear: Optional[str] = None
    arc: Optional[str] = None
    arc_stages: Optional[List[Any]] = None

    strengths: Optional[List[str]] = None
    weaknesses: Optional[List[str]] = None
    special_traits: Optional[List[str]] = None

    known_skills: Optional[List[Any]] = None
    owned_items: Optional[List[Any]] = None

    current_status: Optional[str] = None
    current_location: Optional[str] = None

    author_notes: Optional[str] = None
    extra: Optional[dict] = None


class CharacterOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    alias: List[str]
    role: str
    character_tier: str = "core"   # 旧数据 NULL 时用默认值，避免序列化报错
    gender: Optional[str]
    age: Optional[str]
    avatar_url: Optional[str]

    faction: Optional[str]
    faction_id: Optional[uuid.UUID]
    faction_rank: Optional[str]
    birthplace: Optional[str]

    appearance: Optional[str]
    clothing_style: Optional[str]

    current_realm: Optional[str]
    power_system_id: Optional[uuid.UUID]
    realm_rank: Optional[int]

    personality: Optional[str]
    speech_style: Optional[str]
    values: Optional[str]

    background: Optional[str]
    secrets: Optional[str]
    trauma: Optional[str]

    motivation: Optional[str]
    fear: Optional[str]
    arc: Optional[str]
    arc_stages: List[Any]

    strengths: List[str]
    weaknesses: List[str]
    special_traits: List[str]

    known_skills: List[Any]
    owned_items: List[Any]

    current_status: str
    current_location: Optional[str]

    author_notes: Optional[str]
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
    is_dynamic: str = "stable"
    evolution_note: Optional[str] = None


class RelationshipOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    from_character_id: uuid.UUID
    to_character_id: uuid.UUID
    relation_type: str
    description: Optional[str]
    intensity: int
    is_dynamic: str
    evolution_note: Optional[str]

    class Config:
        from_attributes = True
