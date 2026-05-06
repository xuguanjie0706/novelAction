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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id，归属作品

    promise_text = Column(Text, nullable=False)  # 承诺原文或提炼
    promise_type = Column(String(30), default="chapter_ending")  # 类型: chapter_ending / volume_ending / name_implication / chapter_comment_consensus / protagonist_claim
    source_chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)  # FK → chapters.id，承诺在哪一章埋下
    source_chapter_number = Column(Integer)  # 冗余章号，便于排序/展示（与 source_chapter_id 一致）

    expected_chapter_window = Column(Integer)  # 必须在多少章内兑现（相对源章节序号）
    expected_volume = Column(Integer)  # 或在第几卷内兑现

    status = Column(String(20), default="open")  # open（待兑现）/ fulfilled（已兑现）/ broken（破裂）
    fulfilled_chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)  # FK → chapters.id，在哪一章兑现
    fulfilled_chapter_number = Column(Integer)  # 冗余章号

    priority = Column(Integer, default=3)  # 1–5 优先级（核心承诺权重高）
    audience_aware = Column(Integer, default=3)  # 读者感知度 0–5（埋的时候读者是否明显感到这是承诺）

    extra = Column(JSON, default=dict)  # JSON 扩展字段
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 创建时间（UTC）
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())  # 更新时间（UTC）

    project = relationship("Project", back_populates="reader_promises")
    source_chapter = relationship("Chapter", foreign_keys=[source_chapter_id])
    fulfilled_chapter = relationship("Chapter", foreign_keys=[fulfilled_chapter_id])
