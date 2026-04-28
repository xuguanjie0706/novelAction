from sqlalchemy import Column, String, Text, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(200), nullable=False)
    genre = Column(String(100))                    # 玄幻/都市/科幻...
    logline = Column(Text)                         # 一句话创意
    world_overview = Column(Text)                  # 世界观简述
    story_core = Column(JSON, default=dict)        # 故事核: {drive, conflict, theme, ...}
    status = Column(String(20), default="drafting") # drafting/writing/completed
    target_words = Column(String(20))              # 目标字数
    cover_url = Column(String(500))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Relationships
    world_settings = relationship("WorldSetting", back_populates="project", cascade="all, delete-orphan")
    characters = relationship("Character", back_populates="project", cascade="all, delete-orphan")
    outline_nodes = relationship("OutlineNode", back_populates="project", cascade="all, delete-orphan")
    chapters = relationship("Chapter", back_populates="project", cascade="all, delete-orphan")
    memory_chunks = relationship("MemoryChunk", back_populates="project", cascade="all, delete-orphan")
    # 新增模块
    story_lines = relationship("StoryLine", back_populates="project", cascade="all, delete-orphan")
    power_systems = relationship("PowerSystem", back_populates="project", cascade="all, delete-orphan")
    skills = relationship("Skill", back_populates="project", cascade="all, delete-orphan")
    items = relationship("Item", back_populates="project", cascade="all, delete-orphan")
    factions = relationship("Faction", back_populates="project", cascade="all, delete-orphan")
