"""
chapter_analysis_records — 章节追读/钩子分析历史记录

每次点击「分析」写入一条记录，前端展示时取该章所有记录的均值，
多跑几次可得到更稳定的评估结果。
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.database import Base


class ChapterAnalysisRecord(Base):
    """单次章节综合分析记录（追读模拟 + 章末钩子），支持多次写入后取均值。

    字段约定
    --------
    - score / hook_strength：整数原始值，均值在查询层计算。
    - drop_risk：由本次 score 推导的字符串，不参与均值（均值版用 avg_score 重新推导）。
    - matched_promises_json：MatchedPromise 列表快照（JSON），避免 ReaderPromise 变更后数据漂移。
    - hook_suggestions：建议文本数组（JSON）。
    """

    __tablename__ = "chapter_analysis_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)

    # ── 追读模拟字段 ─────────────────────────────────────────────────────────
    score = Column(Integer, nullable=False)              # 1-10，均值的基础
    will_continue = Column(Boolean, nullable=False)
    drop_risk = Column(String(20), nullable=False)       # low / medium / high（本次推导）
    what_hooked = Column(Text, default="")
    what_repelled = Column(Text, default="")
    verdict = Column(Text, default="")
    hook_tail = Column(Text, default="")                 # 送入模型的章末原文（供调试）

    # ── 钩子检测字段 ─────────────────────────────────────────────────────────
    hook_type = Column(String(30), nullable=False)       # cliffhanger / curiosity / ...
    hook_strength = Column(Integer, nullable=False)      # 1-5，均值的基础
    hook_analysis = Column(Text, default="")
    hook_suggestions = Column(JSONB, default=list)       # List[str]，最多 3 条
    matched_promises_json = Column(JSONB, default=list)  # List[MatchedPromise dict] 快照

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
