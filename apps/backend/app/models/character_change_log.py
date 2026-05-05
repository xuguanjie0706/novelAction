from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database import Base


class CharacterChangeLog(Base):
    """
    人物变更审计日志。

    每次复盘提交或人工编辑导致人物字段变化时写入一条记录，
    changes 数组记录本次所有字段的 before/after，便于按人物或按章节查阅历史。

    source 枚举：
      debrief   — chapter_debrief 自动提交
      manual    — 作者在前端手动编辑保存
      bootstrap — 一句话生成时初始创建
    """
    __tablename__ = "character_change_logs"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    character_id   = Column(UUID(as_uuid=True), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    character_name = Column(String(100), nullable=False)          # 冗余，人物改名后历史仍可读

    # 关联章节（手动编辑时为空）
    chapter_id     = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    chapter_number = Column(String(50),  nullable=True)           # 如「第15章」，冗余存储
    chapter_title  = Column(String(200), nullable=True)

    source  = Column(String(20), nullable=False, default="debrief")  # debrief / manual / bootstrap
    summary = Column(Text, nullable=True)                             # 一句话总结

    # 变更列表，每条：{"field": "current_realm", "label": "境界", "before": "x", "after": "y"}
    changes = Column(JSON, default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_char_changelog_character", "character_id"),
        Index("ix_char_changelog_chapter",   "chapter_id"),
        Index("ix_char_changelog_project",   "project_id"),
    )
