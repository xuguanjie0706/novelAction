from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Faction(Base):
    """
    势力/组织 — 世界中的门派、国家、家族、势力集团等

    faction_type 分类:
      sect        宗门/门派（玄幻常见）
      kingdom     王国/帝国/国家
      family      家族/世家
      guild       商会/公会/组织
      evil        魔道/邪教/反派组织
      race        种族（精灵/魔族/妖族等）
      other       其他

    alignment 阵营立场:
      protagonist 主角阵营
      neutral     中立势力
      antagonist  反派阵营
      unknown     立场不明
    """
    __tablename__ = "factions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键；Character.faction_id 引用
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id
    parent_faction_id = Column(UUID(as_uuid=True), ForeignKey("factions.id"), nullable=True)  # FK → factions.id，上级势力；None=顶层

    name = Column(String(100), nullable=False)            # 势力名称，如"青云宗"
    faction_type = Column(String(20), default="sect")     # sect/kingdom/family/guild/evil/race/other
    alignment = Column(String(20), default="neutral")     # protagonist/neutral/antagonist/unknown

    description = Column(Text)                            # 势力完整描述
    territory = Column(Text)                              # 领地/活动范围

    # 势力实力与规模
    strength_level = Column(String(100))                  # 实力级别，如"顶级宗门，镇守一方"
    member_count = Column(String(50))                     # 成员规模，如"数万弟子"
    top_power = Column(String(100))                       # 最强战力，如"圣人级别"

    # 领导层
    leader_character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=True)  # FK → characters.id，首领/代表
    key_members = Column(JSON, default=list)  # [{character_id, title, note}, ...] → characters.id

    # 势力目标与关系
    goals = Column(Text)                                  # 势力目标与图谋
    resources = Column(Text)                              # 势力资源与特产
    rivals = Column(JSON, default=list)                   # 敌对势力名称列表
    allies = Column(JSON, default=list)                   # 盟友势力名称列表

    # 对主角的关系态度（随剧情变化）
    attitude_to_protagonist = Column(String(20), default="neutral")  # friendly / hostile / neutral / subordinate / superior

    # 势力历史与背景
    history = Column(Text)                               # 势力历史
    secrets = Column(Text)                               # 势力秘密/隐藏目的（作者内部信息）

    sort_order = Column(Integer, default=0)  # 列表排序
    extra = Column(JSON, default=dict)  # JSON 扩展字段

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 创建时间（UTC）
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())  # 更新时间（UTC）

    project = relationship("Project", back_populates="factions")
    parent_faction = relationship("Faction", remote_side=[id], back_populates="sub_factions")
    sub_factions = relationship("Faction", back_populates="parent_faction")
    leader = relationship("Character", foreign_keys=[leader_character_id])
