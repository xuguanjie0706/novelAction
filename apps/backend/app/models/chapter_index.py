from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class ChapterIndex(Base):
    """每章写完后的实际剧情索引，用于连续生成上下文。"""
    __tablename__ = "chapter_indexes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=False, unique=True)  # FK → chapters.id；每章一条剧情索引

    chapter_number = Column(Integer, nullable=False)  # 章序号（与 Chapter.sort_order 对齐）
    story_day = Column(String(100))  # 故事内时间线表述
    core_events = Column(JSON, default=list)  # 本章核心事件列表（结构化）
    first_appearances = Column(JSON, default=list)  # 首次登场的人/物/设定
    actual_foreshadows_laid = Column(JSON, default=list)  # 正文实际新埋伏笔（可与大纲对照）
    actual_foreshadows_resolved = Column(JSON, default=list)  # 正文实际回收伏笔
    ending_hook = Column(Text)  # 章末钩子摘要
    hook_strength = Column(Integer, default=1)  # 钩子强度 1–5 等
    continuity_notes = Column(JSON, default=list)  # 连贯性提醒（供下章生成）

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 索引生成时间（UTC）
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())  # 更新时间（UTC）

    chapter = relationship("Chapter")
