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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)  # FK → chapters.id；删章/解绑可空，章号仍见 source_chapter_number

    source_chapter_number = Column(Integer, nullable=False)  # 问题发现时章节序号（冗余，chapter_id 空时仍可用）
    issue_type = Column(String(80), nullable=False)  # 问题分类（与质检逻辑约定）
    severity = Column(String(20), nullable=False, default="medium")  # 严重度：如 low / medium / high
    status = Column(String(20), nullable=False, default="pending")  # pending / resolved / ignored 等
    summary = Column(Text, nullable=False)  # 问题摘要（给作者与后续生成约束）
    suggested_fix = Column(Text)  # AI/质检建议修复方向
    author_notes = Column(Text)  # 作者处理备注（不覆盖 suggested_fix）
    fingerprint = Column(String(64), nullable=False)  # 与 project_id 组成唯一键，去重同一问题

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 创建时间（UTC）
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())  # 更新时间（UTC）

    chapter = relationship("Chapter")
