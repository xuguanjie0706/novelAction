from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class QualityDebt(Base):
    """质检沉淀出的未解决硬问题，用于后续正文生成约束。"""
    __tablename__ = "quality_debts"
    __table_args__ = (
        UniqueConstraint("project_id", "fingerprint", name="uq_quality_debt_project_fingerprint"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    # 删章或「解除绑定」时置空；source_chapter_number 仍保留来源章号
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)

    source_chapter_number = Column(Integer, nullable=False)
    issue_type = Column(String(80), nullable=False)
    severity = Column(String(20), nullable=False, default="medium")
    status = Column(String(20), nullable=False, default="pending")
    summary = Column(Text, nullable=False)
    suggested_fix = Column(Text)
    author_notes = Column(Text)  # 作者手动修复说明（不覆盖质检 suggested_fix）
    fingerprint = Column(String(64), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    chapter = relationship("Chapter")
