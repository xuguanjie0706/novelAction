"""记忆冲突检测运行日志（每次扫描一条，供管理端与项目内观测）。"""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.sql import func

from app.database import Base


class MemoryConflictDetectLog(Base):
    __tablename__ = "memory_conflict_detect_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True, index=True)

    # manual | chapter_debrief
    trigger = Column(String(40), nullable=False, default="manual", index=True)
    # ok | error | skipped（无记忆条目，未调用 LLM）
    status = Column(String(30), nullable=False, default="ok", index=True)
    duration_ms = Column(Integer, nullable=False, default=0)

    total_chunks_scanned = Column(Integer, nullable=False, default=0)
    conflict_count = Column(Integer, nullable=False, default=0)
    llm_call_log_id = Column(UUID(as_uuid=True), ForeignKey("llm_call_logs.id"), nullable=True)

    error = Column(Text, nullable=True)
    output_payload = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
