from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Character(Base):
    __tablename__ = "characters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)

    # ── 基础信息 ──────────────────────────────────────────────
    name = Column(String(100), nullable=False)
    alias = Column(JSON, default=list)               # 别名/外号列表，如["小火龙","赤焰王"]
    role = Column(String(20), default="supporting")  # protagonist / supporting / antagonist / neutral
    gender = Column(String(20))
    age = Column(String(50))
    avatar_url = Column(String(500))

    # ── 归属 ──────────────────────────────────────────────────
    faction = Column(String(100))                    # 所属势力名（快速引用）
    faction_id = Column(UUID(as_uuid=True), ForeignKey("factions.id"), nullable=True)  # 关联势力表
    faction_rank = Column(String(100))               # 在势力中的地位，如"内门大弟子""副宗主"
    birthplace = Column(String(200))                 # 出生地/来历

    # ── 外貌 ──────────────────────────────────────────────────
    appearance = Column(Text)                        # 外貌描述（身高、容貌、气质、标志性特征）
    clothing_style = Column(Text)                    # 常见服装与风格

    # ── 能力与境界 ────────────────────────────────────────────
    current_realm = Column(String(100))              # 当前境界，如"斗者七星"
    power_system_id = Column(UUID(as_uuid=True), ForeignKey("power_systems.id"), nullable=True)
    realm_rank = Column(Integer)                     # 对应境界体系中的 rank 数字（便于排序比较）

    # ── 性格与说话风格 ────────────────────────────────────────
    personality = Column(Text)                       # 性格特点
    speech_style = Column(Text)                      # 说话风格/口头禅/语气习惯
    values = Column(Text)                            # 价值观、信念、底线

    # ── 背景故事 ──────────────────────────────────────────────
    background = Column(Text)                        # 背景经历
    secrets = Column(Text)                           # 秘密（作者视角，读者未知）
    trauma = Column(Text)                            # 心理创伤/执念

    # ── 动机与成长 ────────────────────────────────────────────
    motivation = Column(Text)                        # 行为动机（想要什么/为什么）
    fear = Column(Text)                              # 恐惧/弱点所在
    arc = Column(Text)                               # 人物弧线整体描述（文字）
    arc_stages = Column(JSON, default=list)
    # 结构化成长阶段：[{stage: "初登场", realm: "淬体境", state: "废柴少年", chapter_range: "1-30"}]

    # ── 能力标签 ──────────────────────────────────────────────
    strengths = Column(JSON, default=list)           # 优点/擅长
    weaknesses = Column(JSON, default=list)          # 缺点/弱点
    special_traits = Column(JSON, default=list)      # 特殊体质/天赋/血脉

    # ── 技能与道具（快速记录，详细信息在 skill/item 表）────────
    known_skills = Column(JSON, default=list)
    # [{skill_id: "uuid", skill_name: "天火流星拳", mastery: "大成"}]
    owned_items = Column(JSON, default=list)
    # [{item_id: "uuid", item_name: "混沌玉简", acquired_chapter: 5}]

    # ── 当前状态 ──────────────────────────────────────────────
    current_status = Column(String(20), default="alive")  # alive/dead/missing/sealed/transformed
    current_location = Column(String(200))            # 当前所在地

    # ── 作者备注 ──────────────────────────────────────────────
    author_notes = Column(Text)                       # 作者内部备注（剧情提醒、避免前后矛盾）

    extra = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project", back_populates="characters")
    faction_obj = relationship("Faction", foreign_keys=[faction_id])
    power_system = relationship("PowerSystem", foreign_keys=[power_system_id])
    relationships_from = relationship(
        "CharacterRelationship",
        foreign_keys="CharacterRelationship.from_character_id",
        cascade="all, delete-orphan"
    )
    relationships_to = relationship(
        "CharacterRelationship",
        foreign_keys="CharacterRelationship.to_character_id",
        cascade="all, delete-orphan"
    )


class CharacterRelationship(Base):
    __tablename__ = "character_relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    from_character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=False)
    to_character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=False)

    relation_type = Column(String(50))    # 师徒 / 敌对 / 恋人 / 兄弟 / 主从 ...
    description = Column(Text)
    intensity = Column(Integer, default=5)    # 1-10 关系强度
    is_dynamic = Column(String(20), default="stable")  # stable/evolving/deteriorating/broken
    # 关系的演变轨迹描述
    evolution_note = Column(Text)

    from_character = relationship("Character", foreign_keys=[from_character_id])
    to_character = relationship("Character", foreign_keys=[to_character_id])
