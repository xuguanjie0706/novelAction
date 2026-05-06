from sqlalchemy import Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class ChapterCoherenceReport(Base):
    __tablename__ = "chapter_coherence_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)  # FK → projects.id
    name = Column(String(200), nullable=False, default="未命名检测")  # 评测任务展示名
    model_profile = Column(String(20), nullable=False, default="local")  # 所用模型配置档：local / remote 等
    selected_chapter_ids = Column(JSON, nullable=False, default=list)  # 参与连贯性检测的 chapter UUID 列表
    result = Column(JSON, nullable=False, default=dict)  # 检测报告主体（结构化结果）
    apply_events = Column(JSON, nullable=False, default=list)  # 从本报告触发的「改正文」应用历史（只追加）
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 报告生成时间（UTC）
