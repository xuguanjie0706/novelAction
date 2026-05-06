from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class OutlineNode(Base):
    """
    大纲树节点，支持任意层级:
      volume (卷) → arc (篇章) → chapter_plan (章节计划)
    parent_id=None 表示根节点（卷级别）
    """
    __tablename__ = "outline_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("outline_nodes.id"), nullable=True)

    node_type = Column(String(20), default="arc")  # volume / arc / chapter_plan
    title = Column(String(300), nullable=False)
    summary = Column(Text)                          # 情节摘要
    hook = Column(Text)                             # 钩子/悬念
    highlight = Column(Text)                        # 燃点/高潮点
    conflict = Column(Text)                         # 冲突
    sort_order = Column(Integer, default=0)

    # ── 追读分析（针对 chapter_plan）──────────────────────────
    reader_hook_score = Column(Integer)             # 1-10 钩子强度预估
    expected_words = Column(Integer)

    # ── 故事线关联 ────────────────────────────────────────────
    storyline_ids = Column(JSON, default=list)      # 本节点推进的故事线 UUID 列表

    # ── 出场人物与道具 ────────────────────────────────────────
    involved_character_ids = Column(JSON, default=list)
    # 本章出场的关键人物 UUID 列表
    key_item_ids = Column(JSON, default=list)
    # 本章涉及的关键道具 UUID 列表
    key_skill_ids = Column(JSON, default=list)
    # 本章涉及的关键技能 UUID 列表（首次亮相/突破/学会）

    # ── 情感与节奏 ────────────────────────────────────────────
    emotional_tone = Column(String(50))
    # 情感基调：exciting/tense/sad/romantic/mysterious/funny/epic/calm

    pacing = Column(String(20), default="normal")
    # 节奏：slow/normal/fast/climax（快节奏、高潮章节特别标记）

    # ── P2 戏份预算与强制 POV（三层调度核心）────────────────────
    character_screen_time = Column(JSON, default=dict)
    # {character_id: 百分比} 本章各角色戏份预算（必须遵守 genre_kit quota）
    pov_character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=True)
    # 本章主要 POV 角色（强制视点，禁止全知）

    # ── 卷阶段标记（OPEN / RISING / TURNING / DARK_HOUR / CLIMAX / ENDING）─
    # 用于章节起草 prompt 模板分流与采样档位选择；章节级允许 override，但通常一卷一阶段。
    # 取值约定（保持英文小写以便与 llm_task_profiles 映射）：
    #   opening    —— 开局期 / 新手村（节奏紧、爽点密、字数偏短）
    #   rising     —— 起飞期 / 扩张期
    #   turning    —— 转折期
    #   dark_hour  —— 至暗期
    #   climax     —— 高潮期
    #   ending     —— 收束期
    phase = Column(String(20))

    # ── 实力里程碑（针对 chapter_plan / arc）────────────────────
    power_milestone = Column(Text)
    # 本节点内主角/重要人物的实力变化，如"主角突破斗者，习得天火流星拳"

    # ── 章节伏笔管理 ──────────────────────────────────────────
    foreshadows_laid = Column(JSON, default=list)
    # 本章埋下的伏笔：[{id: "foreshadow_key", description: "..."}]
    foreshadows_resolved = Column(JSON, default=list)
    # 本章回收的伏笔：[{id: "foreshadow_key", description: "..."}]

    extra = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project", back_populates="outline_nodes")
    parent = relationship("OutlineNode", remote_side=[id], back_populates="children")
    children = relationship("OutlineNode", back_populates="parent", cascade="all, delete-orphan")
    chapter = relationship("Chapter", back_populates="outline_node", uselist=False)
    pov_character = relationship("Character", foreign_keys=[pov_character_id])
    scenes = relationship("Scene", back_populates="outline_node", cascade="all, delete-orphan")
