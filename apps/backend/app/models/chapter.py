from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Float, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键；被 scene/memory/复盘等 FK 引用
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id
    outline_node_id = Column(UUID(as_uuid=True), ForeignKey("outline_nodes.id"), nullable=True)  # FK → outline_nodes.id，对应章节计划节点（可空）

    title = Column(String(300), nullable=False)  # 章节标题
    content = Column(Text, default="")  # 正文（富文本 HTML / Markdown）
    manuscript_raw_snapshot = Column(Text, nullable=True)  # AI 流式原始纯文本快照（含稿末标记），与 content 对照
    word_count = Column(Integer, default=0)  # 正文字数统计
    sort_order = Column(Integer, default=0)  # 全书排序序号（通常即章序）
    status = Column(String(20), default="draft")  # draft / writing / done / reviewed

    last_quality_score = Column(Float)  # 最近一次 AI 质检综合分
    last_quality_report = Column(JSON)  # 质检报告结构化结果
    quality_checked_at = Column(DateTime(timezone=True))  # 最近一次质检时间

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 创建时间（UTC）
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())  # 更新时间（UTC）

    project = relationship("Project", back_populates="chapters")
    outline_node = relationship("OutlineNode", back_populates="chapter")
    versions = relationship("ChapterVersion", back_populates="chapter", cascade="all, delete-orphan")
    ai_chat_messages = relationship("AiChatMessage", back_populates="chapter", cascade="all, delete-orphan")
    scenes = relationship("Scene", back_populates="chapter", cascade="all, delete-orphan")


class ChapterVersion(Base):
    """章节版本历史（每次手动保存创建一个快照）"""
    __tablename__ = "chapter_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=False)  # FK → chapters.id

    content = Column(Text)  # 该版本正文快照
    word_count = Column(Integer)  # 该版本字数
    note = Column(String(200))  # 作者备注（为何保存此版）
    is_auto = Column(Boolean, default=False)  # True=自动快照；False=手动保存

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 快照时间（UTC）

    chapter = relationship("Chapter", back_populates="versions")
