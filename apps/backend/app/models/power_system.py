from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class PowerSystem(Base):
    """
    境界/力量体系 — 世界中的修炼/进化/能力等级体系

    一个项目可以有多套体系（例如斗气 + 魔法双修世界）。

    levels 字段结构（JSON 数组，按境界从低到高排列）：
    [
      {
        "rank": 1,
        "name": "淬体境",
        "description": "打通全身经脉，强化肉身",
        "requirements": "每日修炼基础功法，积累斗气",
        "abilities": ["力量增幅x2", "基础斗技"],
        "approximate_chapter": "前10章"
      },
      ...
    ]
    """
    __tablename__ = "power_systems"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)

    name = Column(String(100), nullable=False)           # 体系名称，如"斗气大陆修炼体系"
    system_type = Column(String(30), default="cultivation")
    # cultivation=修炼/境界  magic=魔法  ability=能力  tech=科技  hybrid=混合

    description = Column(Text)                           # 体系整体简介与世界观地位
    levels = Column(JSON, default=list)                  # 境界列表（见上方结构说明）

    # 体系规则
    cultivation_method = Column(Text)                    # 修炼方式（如：吸收天地灵气、消化兽核）
    breakthrough_condition = Column(Text)                # 突破通用条件
    special_rules = Column(Text)                         # 特殊规则（如：天才/废柴判定方式）

    # 体系在故事中的角色
    protagonist_current_rank = Column(Integer)           # 主角当前在第几境界（rank 数字）
    protagonist_end_rank = Column(Integer)               # 主角预计终点境界

    sort_order = Column(Integer, default=0)
    extra = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project", back_populates="power_systems")
    skills = relationship("Skill", back_populates="power_system")
