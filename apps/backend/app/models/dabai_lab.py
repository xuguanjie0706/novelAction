"""dabai 实验书架写作期产物表（预警 / 质检 / 记忆 / 线索）。

与精品文主链路完全隔离（PreWriteWarningRecord / MemoryChunk / Foreshadow
均绑定 Project，不可复用）。遵循「持久化优先」硬规则：写前导演单、质检
报告、复盘记忆、线索台账全部落库，刷新后可回看。

所有 FK 带 ondelete=CASCADE + passive_deletes，删项目时由 DB 级联清理。
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class DabaiPreWarnRecord(Base):
    """写前导演单记录：每章保留最新一条（重写时覆盖）。"""

    __tablename__ = "dabai_pre_warn_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chapter_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dabai_chapter_outlines.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chapter_number = Column(Integer)
    version = Column(String(40))          # dabai-lab-prewarn-v1
    result = Column(JSON, default=dict)   # fact_lock/conflict_notes/opening_directive/beat_execution/...
    brief = Column(Text)                  # 注入正文 prompt 的简报块（空串=降级未注入）
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DabaiQualityReport(Base):
    """章节质检报告：每章保留最新一条（重跑时覆盖）。"""

    __tablename__ = "dabai_quality_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chapter_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dabai_chapter_outlines.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chapter_number = Column(Integer)
    version = Column(String(40))          # dabai-lab-qc-v1
    status = Column(String(20))           # ok / warning / blocked
    overall_score = Column(Integer)       # 衔接40% + 五拍40% + 钩子20%
    report = Column(JSON, default=dict)   # 完整报告（blockers/warnings/llm/...）
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DabaiMemory(Base):
    """复盘记忆条目：章级幂等（重跑复盘先删同章旧记忆）。"""

    __tablename__ = "dabai_memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chapter_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dabai_chapter_outlines.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    chapter_number = Column(Integer, index=True)
    mem_type = Column(String(20), default="event")   # fact / event / state / relation
    content = Column(Text, nullable=False)
    importance = Column(Integer, default=3)          # 1-5
    tags = Column(JSON, default=list)                # 涉及人名等
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DabaiAsset(Base):
    """资产台账（功法技能 / 道具法宝 / 金手指能力），防能力与装备漂移。

    owner 用人名字符串（lab 人物无独立 FK 需求）；种子来自 golden_finger /
    power_ladder / characters（source=seed），写作期由复盘维护（source=debrief）。
    """

    __tablename__ = "dabai_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    kind = Column(String(20), default="item")         # skill / item / golden_finger
    name = Column(String(120), nullable=False)
    owner = Column(String(100))                       # 持有者人名（通常主角）
    description = Column(Text)
    acquired_chapter = Column(Integer)                # 获得章号（seed 为空）
    status = Column(String(20), default="active")     # active / consumed / lost
    status_chapter = Column(Integer)                  # 最近状态变化章号
    source = Column(String(20), default="debrief")    # seed / debrief / manual
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class DabaiRelation(Base):
    """人物关系台账：主角视角的态度轨迹（敌对→臣服→效忠是爽点核心曲线）。

    (from_name, to_name) 项目内唯一逻辑键；attitude 为最新态度，
    history 追加 {chapter, attitude, reason} 保留完整轨迹。
    """

    __tablename__ = "dabai_relations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    from_name = Column(String(100), nullable=False)   # 通常为主角
    to_name = Column(String(100), nullable=False)
    attitude = Column(String(40))                     # 敌对/轻视/忌惮/臣服/效忠/盟友/暧昧...
    note = Column(Text)
    last_change_chapter = Column(Integer)
    history = Column(JSON, default=list)              # [{chapter, attitude, reason}]
    source = Column(String(20), default="debrief")    # seed / debrief / manual
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class DabaiClue(Base):
    """线索/伏笔台账：复盘自动埋设与回收，支持手动改状态。"""

    __tablename__ = "dabai_clues"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    title = Column(String(200), nullable=False)
    clue_type = Column(String(20), default="hook")   # hook / foreshadow / promise
    description = Column(Text)
    chapter_planted = Column(Integer)                # 埋设章号
    chapter_resolved = Column(Integer)               # 回收章号（open 时为空）
    status = Column(String(20), default="open")      # open / resolved / dropped
    source = Column(String(20), default="debrief")   # debrief / manual
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
