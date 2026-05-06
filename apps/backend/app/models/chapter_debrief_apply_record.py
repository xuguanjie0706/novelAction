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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)  # FK → projects.id
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)  # FK → chapters.id，复盘目标章
    apply_source = Column(String(32), nullable=False, default="manual_tab")  # 提交来源：如 manual_tab / queue_auto 等
    content_hash = Column(String(64), nullable=True)  # 提交内容哈希，用于判重或对照缓存
    payload = Column(JSON, nullable=False, default=dict)  # 当时提交的完整复盘载荷快照
    result_message = Column(Text, nullable=True)  # 服务端处理结果说明（成功/失败原因）
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 提交成功时间（UTC）
