"""
ReaderPromise 表 — 读者期待管理（网文核心工序）

记录作者/章节对读者公开做过的承诺：
- 章末预告（下一章必须兑现）
- 卷末预告（本卷必须兑现）
- 名字/技能/称号暗示（叫“剑神”就必须有封神桥段）
- 章评共识（读者高频追问的“什么时候打X”）

写章时 prompt 注入“本章必须/可以兑现的承诺额度”；
复盘自动检测新承诺、回收旧承诺、标记破裂。
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class ReaderPromise(Base):
    __tablename__ = "reader_promises"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)

    # 承诺内容
    promise_text = Column(Text, nullable=False)          # 承诺原文或提炼
    promise_type = Column(String(30), default="chapter_ending")  # chapter_ending / volume_ending / name_implication / chapter_comment_consensus / protagonist_claim
    source_chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)
    source_chapter_number = Column(Integer)

    # 预期兑现窗口
    expected_chapter_window = Column(Integer)            # 必须在多少章内兑现（相对 source_chapter_number）
    expected_volume = Column(Integer)                    # 或在第几卷内

    # 状态
    status = Column(String(20), default="open")          # open / fulfilled / broken
    fulfilled_chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)
    fulfilled_chapter_number = Column(Integer)

    # 优先级与读者感知
    priority = Column(Integer, default=3)                # 1=低 … 5=核心承诺
    audience_aware = Column(Integer, default=3)          # 读者感知度 0-5（埋的时候读者是否明显感觉到这是承诺）

    extra = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project", back_populates="reader_promises")
    source_chapter = relationship("Chapter", foreign_keys=[source_chapter_id])
    fulfilled_chapter = relationship("Chapter", foreign_keys=[fulfilled_chapter_id])
