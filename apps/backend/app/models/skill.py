from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Skill(Base):
    """
    功法/技能 — 世界中存在的战斗技能、修炼功法、辅助能力等

    skill_type 分类:
      combat      攻击类（拳法、剑法、掌法）
      defense     防御类（护体功、盾技）
      movement    身法类（轻功、步法、瞬移）
      support     辅助类（疗伤、增益、炼丹）
      bloodline   血脉/体质类（先天神脉、觉醒技能）
      special     特殊类（禁术、逆天技能）

    grade 品阶（由低到高）:
      mortal      凡品
      earth       地品
      sky         天品
      profound    玄品
      saint       圣品
      divine      神品
      supreme     无上
    """
    __tablename__ = "skills"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    power_system_id = Column(UUID(as_uuid=True), ForeignKey("power_systems.id"), nullable=True)

    name = Column(String(100), nullable=False)           # 技能名，如"天火流星拳"
    skill_type = Column(String(20), default="combat")    # combat/defense/movement/support/bloodline/special
    grade = Column(String(20), default="earth")          # 品阶
    source = Column(String(200))                         # 来源，如"上古秘典""师门传承"

    # 修炼要求
    level_required = Column(String(100))                 # 需要达到的境界，如"斗者三星"
    prerequisites = Column(Text)                         # 其他前置条件

    # 技能详情
    description = Column(Text)                          # 功法/技能完整描述
    effects = Column(Text)                              # 使用效果
    limitations = Column(Text)                          # 限制与副作用（如消耗、反噬、禁忌）
    mastery_stages = Column(JSON, default=list)
    # 修炼阶段：[{stage: "入门", effect: "威力30%"}, {stage: "大成", effect: "威力100%"}]

    # 掌握此技能的人物（character_id 列表）
    mastered_by_character_ids = Column(JSON, default=list)

    # 故事中首次出现的章节
    first_appearance_chapter = Column(Integer)

    sort_order = Column(Integer, default=0)
    extra = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project", back_populates="skills")
    power_system = relationship("PowerSystem", back_populates="skills")
