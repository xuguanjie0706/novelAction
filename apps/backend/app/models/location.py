"""
Location 模型 — 空间连续性机制

设计动机（来自30年作家视角）：
  位置不只是地名标签，而是「感官基准 + 危险等级 + 控制方」三位一体的叙事约束。
  本模型通过 sensory_signature 给每个场景地点固定感官描述（1-3句），
  写章时注入 prompt 作为硬约束，防止正文在同一地点出现感知漂移
  （如藏经阁第一章"木质气息/烛光"，第五章变成"石板冰冷/明亮"——AI 味的典型来源）。

与现有系统的连接：
  - Character.current_location (str)   → 复盘时提取，写章时按名称/别名与 Location 匹配
  - Scene.location_id (UUID, FK)       → 精确关联本表；Bootstrap/旧数据可仅用 location_name 文本兜底
  - Scene.location_name (str)          → 与 location_id 并存，便于展示与未建库地点时的自由文本
  - 写章 prompt：_build_location_context() 在 gated_draft_routes.py 注入硬约束块
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Location(Base):
    """场景地点 — 空间连续性管理的核心单元。"""

    __tablename__ = "locations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)

    # ── 基本标识 ────────────────────────────────────────────────────────────────
    name = Column(String(100), nullable=False)           # 地点名（唯一可读标识）
    aliases = Column(JSON, default=list)                 # 别名列表（方便模糊匹配角色 current_location）

    # ── 地点分类 ────────────────────────────────────────────────────────────────
    location_type = Column(String(30), default="indoor")
    # indoor / outdoor / ruins / battlefield / wilderness / sacred_ground / city / dungeon / void

    # ── 层级结构（支持"天玄宗 → 藏经阁 → 禁区"三级嵌套）──────────────────────
    parent_location_id = Column(
        UUID(as_uuid=True),
        ForeignKey("locations.id"),
        nullable=True,
    )

    # ── 叙事属性 ────────────────────────────────────────────────────────────────
    danger_level = Column(String(20), default="neutral")
    # safe / neutral / dangerous / forbidden

    controller = Column(String(100))
    # 当前控制方（宗门名/势力名/"混乱"），影响角色进入逻辑

    # ── 核心防漂移字段 ──────────────────────────────────────────────────────────
    sensory_signature = Column(Text)
    # 固定感官基准（1-3句）。写章时注入为硬约束：
    # 例："古朴木质气息，烛光昏黄，偶有翻页声；地面踩踏无声，书架延伸至穹顶。"
    # AI 在此地点写作时必须与该描述一致，不得引入矛盾感官细节。

    # ── 叙事状态 ────────────────────────────────────────────────────────────────
    description = Column(Text)                          # 地点详细描述（背景/历史/特殊规则）
    status = Column(String(20), default="active")
    # active / destroyed / occupied / abandoned / sealed

    # ── 排序 ────────────────────────────────────────────────────────────────────
    sort_order = Column(Integer, default=0)              # 前端展示排序

    extra = Column(JSON, default=dict)                   # 预留扩展（如地图坐标、可达路线等）

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ── Relationships ────────────────────────────────────────────────────────────
    project = relationship("Project", back_populates="locations")
    parent = relationship("Location", remote_side=[id], back_populates="children")
    children = relationship("Location", back_populates="parent")
    scenes = relationship("Scene", back_populates="location")
