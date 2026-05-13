from sqlalchemy import Column, String, Text, DateTime, JSON, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键；被 chapters/characters/outline 等 FK 引用
    # 项目归属用户：多租户隔离的核心字段。NULL 仅出现在多租户上线前的遗留数据上，
    # 启动迁移会把这类记录归到最早注册的 active 用户；新建项目此列必填。
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(200), nullable=False)  # 书名/项目名
    genre = Column(String(100))  # 题材标签，如玄幻/都市/科幻
    logline = Column(Text)  # 一句话梗概（对外 pitch）
    premise = Column(Text)  # 立意：定位、主题、禁忌边界
    world_overview = Column(Text)  # 世界观简述（给 AI/作者速览）
    story_core = Column(JSON, default=dict)  # 故事核 JSON：drive / conflict / theme 等
    status = Column(String(20), default="drafting")  # 作品阶段: drafting / writing / completed
    target_words = Column(Integer, default=1200000)  # 目标总字数
    cover_url = Column(Text)  # 封面 URL 或 data URL（长 base64 故用 Text）
    extra = Column(JSON, default=dict)  # JSON 扩展；如 positioning（受众/梗/打脸节奏等立项字段）

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 创建时间（UTC）
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())  # 更新时间（UTC）

    # Relationships
    world_settings = relationship("WorldSetting", back_populates="project", cascade="all, delete-orphan")
    characters = relationship("Character", back_populates="project", cascade="all, delete-orphan")
    outline_nodes = relationship("OutlineNode", back_populates="project", cascade="all, delete-orphan")
    chapters = relationship("Chapter", back_populates="project", cascade="all, delete-orphan")
    memory_chunks = relationship("MemoryChunk", back_populates="project", cascade="all, delete-orphan")
    ai_chat_messages = relationship("AiChatMessage", back_populates="project", cascade="all, delete-orphan")
    # 新增模块
    story_lines = relationship("StoryLine", back_populates="project", cascade="all, delete-orphan")
    power_systems = relationship("PowerSystem", back_populates="project", cascade="all, delete-orphan")
    skills = relationship("Skill", back_populates="project", cascade="all, delete-orphan")
    items = relationship("Item", back_populates="project", cascade="all, delete-orphan")
    factions = relationship("Faction", back_populates="project", cascade="all, delete-orphan")
    scenes = relationship("Scene", back_populates="project", cascade="all, delete-orphan")
    reader_promises = relationship("ReaderPromise", back_populates="project", cascade="all, delete-orphan")
    locations = relationship("Location", back_populates="project", cascade="all, delete-orphan")
