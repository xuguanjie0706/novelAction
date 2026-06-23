"""
chapter_debrief_undo — 复盘提交前的状态快照，用于删章/重写时回滚。

存储内容：
  - char_states: 提交前全部既有人物的境界、位置、状态与复盘可变 JSON 字段
  - storyline_statuses: 提交前被改动故事线的 status / key_beats

全人物快照用于兜住 chapter_index 补全与 realm_plan_floor 等非显式人物更新；
带 chapter_id 的增量仍会额外按来源过滤，形成双保险。
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class ChapterDebriefUndo(Base):
    __tablename__ = "chapter_debrief_undos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)  # FK → projects.id
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, unique=True)  # FK → chapters.id；每章最多一条回滚快照

    char_states = Column(JSON, nullable=False, default=list)  # 复盘提交前全部既有人物的可变字段快照

    storyline_statuses = Column(JSON, nullable=False, default=list)  # 提交前故事线状态与 key_beats

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 快照生成时间（UTC）
