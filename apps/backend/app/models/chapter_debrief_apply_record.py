from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class ChapterDebriefApplyRecord(Base):
    """
    每次复盘提交（chapter-debrief）成功后的审计快照：记录当时提交的填入内容，
    便于区分「队列自动」与「Tab 手动」并做历史回溯。
    """

    __tablename__ = "chapter_debrief_apply_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    apply_source = Column(String(32), nullable=False, default="manual_tab")
    content_hash = Column(String(64), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    result_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
