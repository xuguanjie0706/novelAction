from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class ChapterIndex(Base):
    """每章写完后的实际剧情索引，用于连续生成上下文。"""
    __tablename__ = "chapter_indexes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=False, unique=True)

    chapter_number = Column(Integer, nullable=False)
    story_day = Column(String(100))
    core_events = Column(JSON, default=list)
    first_appearances = Column(JSON, default=list)
    actual_foreshadows_laid = Column(JSON, default=list)
    actual_foreshadows_resolved = Column(JSON, default=list)
    ending_hook = Column(Text)
    hook_strength = Column(Integer, default=1)
    continuity_notes = Column(JSON, default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    chapter = relationship("Chapter")
