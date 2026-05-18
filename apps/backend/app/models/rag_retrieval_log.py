"""RAG 记忆检索调用日志（写章 / 质检 / 手动查询）。"""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.sql import func

from app.database import Base


class RagRetrievalLog(Base):
    __tablename__ = "rag_retrieval_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True, index=True)

    # draft_context | pre_write_warning | suggest | rag_query
    source = Column(String(40), nullable=False, default="rag_query", index=True)
    status = Column(String(30), nullable=False, default="ok")
    duration_ms = Column(Integer, nullable=False, default=0)

    input_payload = Column(JSON, nullable=False, default=dict)
    output_payload = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
