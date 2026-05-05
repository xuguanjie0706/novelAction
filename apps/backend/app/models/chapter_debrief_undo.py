"""
chapter_debrief_undo — 复盘提交前的状态快照，用于删章/重写时回滚。

存储内容：
  - char_states: 提交前每个被改动人物的 realm/location/status/realm_rank
  - storyline_statuses: 提交前每条被改动故事线的 status

beats / known_skills / owned_items 的回滚通过 "chapter_id" / "from_chapter_id"
字段直接过滤，不需要存快照。
"""
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class ChapterDebriefUndo(Base):
    __tablename__ = "chapter_debrief_undos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, unique=True)

    # [{ "character_id": "...", "current_realm": "筑基期", "current_location": "...",
    #    "current_status": "alive", "realm_rank": 3 }, ...]
    char_states = Column(JSON, nullable=False, default=list)

    # [{ "storyline_id": "...", "status": "ongoing" }, ...]
    storyline_statuses = Column(JSON, nullable=False, default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
