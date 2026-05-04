from sqlalchemy import Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class ChapterCoherenceReport(Base):
    __tablename__ = "chapter_coherence_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False, default="未命名检测")
    model_profile = Column(String(20), nullable=False, default="local")
    selected_chapter_ids = Column(JSON, nullable=False, default=list)
    result = Column(JSON, nullable=False, default=dict)
    # 根据本评测「改正文」写入数据库的历史（append-only，便于在阅读评测页回顾）
    apply_events = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
