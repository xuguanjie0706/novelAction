"""dabai 实验书架写作期产物表（预警 / 质检 / 记忆 / 线索 / 台账 / 面板快照）。

与精品文主链路完全隔离（PreWriteWarningRecord / MemoryChunk / Foreshadow
均绑定 Project，不可复用）。遵循「持久化优先」硬规则：写前导演单、质检
报告、复盘记忆、线索台账、系统面板快照全部落库，刷新后可回看。

所有 FK 带 ondelete=CASCADE + passive_deletes，删项目时由 DB 级联清理。

资产品阶枚举（grade 字段）：
  0 = 凡品  1 = 灵品  2 = 仙品  3 = 神品  4 = 传说/天外
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


class DabaiScenePlan(Base):
    """章节分场调度单：每章保留最新一条（重写时覆盖）。

    五拍章纲 → 2-4 场分场 → 逐场正文，是「章纲一句话直接糊 2000 字」的解药。
    scenes JSON 结构（v1）：
    [{"order": 1, "name": "场名", "location": "地点", "characters_on_stage": [...],
      "goal": "本场承担的节拍", "event": "发生什么（具体动作链）",
      "dialogue_ammo": ["关键台词原话 2-3 句"], "sensory_anchor": "1个感官细节锚点",
      "end_turn": "本场结尾的转折/递进", "word_budget": 600}]
    """

    __tablename__ = "dabai_scene_plans"

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
    version = Column(String(40))          # dabai-lab-sceneplan-v1
    scenes = Column(JSON, default=list)   # 分场列表（见类 docstring）
    opening_line = Column(Text)           # 开篇第一句指令（前3行进冲突）
    brief = Column(Text)                  # 注入正文 prompt 的分场块（空串=降级未注入）
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DabaiQualityReport(Base):
    """章节质检报告：每次质检追加一条（保留历史，供后台回归）。"""

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
    chapter_number = Column(Integer, index=True)
    version = Column(String(40))          # dabai-lab-qc-v1
    status = Column(String(20))           # ok / warning / blocked
    overall_score = Column(Integer)       # 衔接40% + 五拍40% + 钩子20%
    source = Column(String(30), default="manual")  # manual / post_write / rules
    content_word_count = Column(Integer)
    content_head_preview = Column(Text)   # 质检时刻正文开头（便于后台 diff）
    report = Column(JSON, default=dict)   # 完整报告（blockers/warnings/llm/continuity_snapshot/...）
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


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

    # ── 系统文数值字段（v2，2026-06）──────────────────────────────────────────
    # grade: 品阶数值 0=凡品 1=灵品 2=仙品 3=神品 4=传说；None=未定级
    grade = Column(Integer, nullable=True)
    # base_stat: 基础属性加成，如 {"atk": 200, "def": 50, "desc": "攻击+200"}
    base_stat = Column(JSON, nullable=True)
    # cooldown_chapters: 技能冷却章数（0=无冷却；None=被动技能不适用）
    cooldown_chapters = Column(Integer, nullable=True)
    # last_used_chapter: 最近一次使用章号（用于判断冷却是否结束）
    last_used_chapter = Column(Integer, nullable=True)
    # enhancement_level: 强化/升阶层数（0=未强化）
    enhancement_level = Column(Integer, default=0)

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


class DabaiPanelSnapshot(Base):
    """系统面板快照：每章复盘完成后存一条，作为下章写作的绝对基准。

    snapshot JSON 结构（v1）：
    {
      "realm": "筑基期",
      "sub_level": 3,           # 小境界层数
      "max_sub": 9,             # 该大境界最大层数
      "combat_power": 5800,     # 战力估算
      "skills": [               # 主角 active 技能列表（含冷却状态）
        {"name": "...", "grade": 1, "cooldown_chapters": 2,
         "last_used_chapter": 47, "on_cooldown": true}
      ],
      "items": [                # 主角 active 道具/法宝列表
        {"name": "...", "grade": 2, "base_stat": {...}}
      ],
      "golden_fingers": [       # 金手指
        {"name": "...", "description": "..."}
      ]
    }
    """

    __tablename__ = "dabai_panel_snapshots"

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
    snapshot = Column(JSON, default=dict)       # 结构化系统面板数据（见类 docstring）
    created_at = Column(DateTime(timezone=True), server_default=func.now())
