"""大白文（爽点节拍器）独立数据表 —— dabai_* 前缀。

设计原则：与精品文主链路**完全隔离**，自成一套表，不复用 Project/OutlineNode。
  - dabai_projects        一本大白文一行，单例/短列表设定（定位/金手指/境界/势力/
                          人物/故事线/linter 报告）以 JSON 列存储，生成即定，整块展示。
  - dabai_volumes         卷骨架（每卷爽点大节拍 + 卷末高潮）。
  - dabai_chapter_outlines 章纲，爽点节拍器字段为**独立列**（便于查询/质检），
                          ★没有 choice_cost★，这是与主仓库 OutlineNode 的根本区别。
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class DabaiProject(Base):
    """一本大白文项目（独立于精品文 Project）。"""

    __tablename__ = "dabai_projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=True)  # 归属用户（按 Bearer 解析；不强外键，保持独立）

    logline = Column(Text, nullable=False)               # 一句话创意
    title = Column(String(120))                          # 书名（可由定位推导，先留空）
    status = Column(String(20), default="generated")     # generating / generated / failed
    mock = Column(Boolean, default=False)                # 是否离线 mock 产物

    # ── 单例设定（生成即定，整体展示，JSON 列）────────────────────────────────
    benchmark = Column(JSON, default=dict)               # 对标分析（对标书+文笔/设定特征）
    positioning = Column(JSON, default=dict)             # 立项定位
    golden_finger = Column(JSON, default=dict)           # 金手指（大白文爽点引擎）
    power_ladder = Column(JSON, default=dict)            # 境界阶梯
    linter_report = Column(JSON, default=dict)           # 大白文 linter 报告
    meta = Column(JSON, default=dict)                    # 卷数/章数/模型/失败步骤等
    failed_steps = Column(JSON, default=list)            # 失败步骤名
    extra = Column(JSON, default=dict)                   # 规划层杂物：antagonist_ladder /
    #   mystery_schedule / title_blurb / beat_sequence_vol{N}（卷展开重建 ctx 时回读）
    # 注：factions / characters / storylines 已拆为独立表（见下），不再用 JSON 列。

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    factions = relationship(
        "DabaiFaction", back_populates="project",
        cascade="all, delete-orphan", order_by="DabaiFaction.sort_order",
    )
    characters = relationship(
        "DabaiCharacter", back_populates="project",
        cascade="all, delete-orphan", order_by="DabaiCharacter.sort_order",
    )
    storylines = relationship(
        "DabaiStoryline", back_populates="project",
        cascade="all, delete-orphan", order_by="DabaiStoryline.sort_order",
    )
    volumes = relationship(
        "DabaiVolume", back_populates="project",
        cascade="all, delete-orphan", order_by="DabaiVolume.volume_number",
    )
    chapter_outlines = relationship(
        "DabaiChapterOutline", back_populates="project",
        cascade="all, delete-orphan", order_by="DabaiChapterOutline.chapter_number",
    )


class DabaiFaction(Base):
    """势力（压迫主角的土壤 / 打脸对象来源）。"""

    __tablename__ = "dabai_factions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(100), nullable=False)
    stance = Column(String(40))          # 主角方/压迫方/中立资源/神秘势力
    role = Column(Text)                  # 在爽点循环里的作用
    power_tier = Column(String(100))     # 最高战力档
    note = Column(Text)                  # 前期/后期作用
    locations = Column(JSON, default=list)  # 驻地+周边场景池（章纲 location 轮换素材）
    sort_order = Column(Integer, default=0)

    project = relationship("DabaiProject", back_populates="factions")


class DabaiCharacter(Base):
    """人物（主角 / 打脸对象 / 女主 / 工具人）。"""

    __tablename__ = "dabai_characters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(100), nullable=False)
    role = Column(String(60))            # 主角/打脸对象/女主/导师/工具人配角
    tier = Column(String(20))            # 核心/配角
    start_realm = Column(String(60))     # 起始境界
    persona = Column(Text)               # 性格
    function = Column(Text)              # 在爽点循环里的功能
    extra = Column(JSON, default=dict)   # desire/wound/golden_finger 等附加（主角）
    sort_order = Column(Integer, default=0)

    project = relationship("DabaiProject", back_populates="characters")


class DabaiStoryline(Base):
    """故事线（主线升级打脸 + 复仇/感情/身世）。"""

    __tablename__ = "dabai_storylines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(120), nullable=False)
    type = Column(String(30))            # main/revenge/romance/mystery
    summary = Column(Text)
    nodes = Column(JSON, default=list)   # 关键节点 [{planned_volume, node}]（卷骨架/章纲落位依据）
    bound_characters = Column(JSON, default=list)  # 线绑定人物名
    sort_order = Column(Integer, default=0)

    project = relationship("DabaiProject", back_populates="storylines")


class DabaiVolume(Base):
    """卷骨架：每卷的爽点大节拍与卷末高潮。"""

    __tablename__ = "dabai_volumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    volume_number = Column(Integer, nullable=False)      # 卷序（1-based）
    title = Column(String(200))
    phase = Column(String(20))                           # opening/rising/turning/dark_hour/climax
    planned_chapters = Column(Integer, default=30)
    big_beats = Column(JSON, default=list)               # 本卷大爆点
    volume_climax = Column(Text)                         # 卷末高潮
    end_hook = Column(Text)                              # 卷末钩子
    # ── 境界脊柱（主角本卷境界区间，对应 power_ladder.levels.rank）──
    realm_start_rank = Column(Integer)                   # 卷初主角境界档
    realm_end_rank = Column(Integer)                     # 卷末主角境界档（≥start，跨卷单调）
    extra = Column(JSON, default=dict)                   # boss / storyline_moves / mystery_moves

    project = relationship("DabaiProject", back_populates="volumes")


class DabaiChapterOutline(Base):
    """章纲：爽点节拍器。每个字段都是大白文的命门，**无 choice_cost**。"""

    __tablename__ = "dabai_chapter_outlines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True), ForeignKey("dabai_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    volume_id = Column(
        UUID(as_uuid=True), ForeignKey("dabai_volumes.id", ondelete="CASCADE"),
        nullable=True,
    )

    chapter_number = Column(Integer, nullable=False)     # 卷内章序
    title = Column(String(120))

    # ── 爽点节拍器四拍（本表核心）──────────────────────────────────────────────
    shuang_type = Column(String(40))                     # 一等公民：本章爽点类型
    location = Column(String(120))                       # 场景载体（地点+事件，相邻章轮换防同质化）
    yaqu_setup = Column(Text)                            # 憋屈势能（前置弹簧）
    emotion_turn = Column(Text)                          # 转折拍：情绪扳机（从X情绪→靠什么触发→转到Y情绪）
    yinbao = Column(Text)                                # 引爆：怎么反转
    shuang_payoff = Column(Text)                         # 爽感量化（须有观众）
    witnesses = Column(JSON, default=list)               # 见证者/被打脸者
    end_hook = Column(Text)                              # 章末强钩子

    new_info_count = Column(Integer, default=1)          # 信息密度
    involved_characters = Column(JSON, default=list)
    is_big_beat = Column(Boolean, default=False)         # 大爆点
    expected_words = Column(Integer, default=2000)
    realm_rank = Column(Integer)                         # 主角本章境界档（指向 power_ladder.levels.rank；全书单调不减）

    # ── 正文（写作期填充）──────────────────────────────────────────────────────
    content = Column(Text)                               # 生成的章节正文
    status = Column(String(20), default="planned")       # planned / written

    project = relationship("DabaiProject", back_populates="chapter_outlines")
    volume = relationship("DabaiVolume")
