"""写前预警历史：每次「预警」落库一条，便于写作页再次打开时查阅。"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.database import Base


class PreWriteWarningRecord(Base):
    __tablename__ = "pre_write_warning_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)  # FK → projects.id
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)  # FK → chapters.id
    chapter_number = Column(Integer, nullable=False, default=0)  # 冗余章序，删库后仍可辨

    chapter_plan_summary = Column(Text, nullable=False, default="")  # 本次检测使用的计划摘要
    model_profile = Column(String(20), nullable=False, default="local")  # local / gemini 等
    llm_provider_id = Column(String(36), nullable=True)  # 可选，与 LlmProvider.id 字符串一致

    result = Column(JSONB, nullable=False)  # { ok, risk_count, risks, reminders, error?, raw? }

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # 写入时间（UTC）
