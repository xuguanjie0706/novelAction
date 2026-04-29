from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Foreshadow(Base):
    """全局伏笔管理表 — 跨章节追踪所有伏笔的埋设与回收状态。"""
    __tablename__ = "foreshadows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)

    # 基础信息
    code = Column(String(20))             # 自动编号，如 F-001
    title = Column(String(200), nullable=False)
    description = Column(Text)

    # 埋设章节
    laid_chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)
    laid_chapter_number = Column(Integer)   # 冗余，便于查询排序

    # 回收章节
    resolved_chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)
    resolved_chapter_number = Column(Integer)   # 冗余
    planned_resolve_chapter = Column(Integer)   # 预计回收章节号

    # 状态与优先级
    status = Column(String(20), default="open")  # open / resolved / dropped
    priority = Column(Integer, default=3)         # 1=低 … 5=关键主线

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    laid_chapter = relationship("Chapter", foreign_keys=[laid_chapter_id], lazy="select")
    resolved_chapter = relationship("Chapter", foreign_keys=[resolved_chapter_id], lazy="select")
