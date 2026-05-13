"""Location Pydantic schemas — 地点 CRUD 请求/响应契约。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class LocationCreate(BaseModel):
    """创建地点请求体。"""

    name: str = Field(..., max_length=100, description="地点名称")
    aliases: Optional[List[str]] = Field(default_factory=list, description="别名列表（用于角色位置模糊匹配）")
    location_type: Optional[str] = Field(default="indoor", description="地点类型：indoor/outdoor/ruins/battlefield/wilderness/sacred_ground/city/dungeon/void")
    parent_location_id: Optional[UUID] = Field(default=None, description="父级地点 UUID（层级嵌套）")
    danger_level: Optional[str] = Field(default="neutral", description="危险等级：safe/neutral/dangerous/forbidden")
    controller: Optional[str] = Field(default=None, max_length=100, description="控制方（势力/宗门）")
    sensory_signature: Optional[str] = Field(default=None, description="固定感官基准（1-3句），写章时注入硬约束")
    description: Optional[str] = Field(default=None, description="地点详细描述")
    status: Optional[str] = Field(default="active", description="地点状态：active/destroyed/occupied/abandoned/sealed")
    sort_order: Optional[int] = Field(default=0, description="前端展示排序")
    extra: Optional[Dict[str, Any]] = Field(default_factory=dict, description="扩展字段")


class LocationUpdate(BaseModel):
    """更新地点请求体（全部字段可选）。"""

    name: Optional[str] = Field(default=None, max_length=100)
    aliases: Optional[List[str]] = None
    location_type: Optional[str] = None
    parent_location_id: Optional[UUID] = None
    danger_level: Optional[str] = None
    controller: Optional[str] = None
    sensory_signature: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None
    extra: Optional[Dict[str, Any]] = None


class LocationOut(BaseModel):
    """地点响应体。"""

    id: UUID
    project_id: UUID
    name: str
    aliases: Optional[List[str]] = None
    location_type: Optional[str] = None
    parent_location_id: Optional[UUID] = None
    danger_level: Optional[str] = None
    controller: Optional[str] = None
    sensory_signature: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None
    extra: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
