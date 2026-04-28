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

    name = Column(String(100), nullable=False)
    role = Column(String(20), default="supporting")  # protagonist / supporting / antagonist
    gender = Column(String(20))
    age = Column(String(50))
    faction = Column(String(100))                  # 所属势力
    avatar_url = Column(String(500))

    # 人物设定
    personality = Column(Text)                     # 性格
    background = Column(Text)                      # 背景
    motivation = Column(Text)                      # 动机
    arc = Column(Text)                             # 人物弧线（成长轨迹）
    strengths = Column(JSON, default=list)         # 优点列表
    weaknesses = Column(JSON, default=list)        # 缺点/弱点列表
    special_traits = Column(JSON, default=list)    # 特殊能力/特征
    extra = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project", back_populates="characters")
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

    relation_type = Column(String(50))    # 师徒 / 敌对 / 恋人 / 兄弟 ...
    description = Column(Text)
    intensity = Column(Integer, default=5)  # 1-10 关系强度

    from_character = relationship("Character", foreign_keys=[from_character_id])
    to_character = relationship("Character", foreign_keys=[to_character_id])
