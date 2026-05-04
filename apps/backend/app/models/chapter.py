from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Float, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    outline_node_id = Column(UUID(as_uuid=True), ForeignKey("outline_nodes.id"), nullable=True)

    title = Column(String(300), nullable=False)
    content = Column(Text, default="")             # 正文（富文本 HTML / Markdown）
    # 最近一次 AI 流式返回的完整纯文本（含稿末 ### ch_ 等），与 content 分离入库，便于对照
    manuscript_raw_snapshot = Column(Text, nullable=True)
    word_count = Column(Integer, default=0)
    sort_order = Column(Integer, default=0)
    status = Column(String(20), default="draft")   # draft / writing / done / reviewed

    # AI 质检结果缓存
    last_quality_score = Column(Float)
    last_quality_report = Column(JSON)
    quality_checked_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project", back_populates="chapters")
    outline_node = relationship("OutlineNode", back_populates="chapter")
    versions = relationship("ChapterVersion", back_populates="chapter", cascade="all, delete-orphan")
    ai_chat_messages = relationship("AiChatMessage", back_populates="chapter", cascade="all, delete-orphan")


class ChapterVersion(Base):
    """章节版本历史（每次手动保存创建一个快照）"""
    __tablename__ = "chapter_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=False)

    content = Column(Text)
    word_count = Column(Integer)
    note = Column(String(200))                     # 版本备注
    is_auto = Column(Boolean, default=False)       # 是否自动快照

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    chapter = relationship("Chapter", back_populates="versions")
