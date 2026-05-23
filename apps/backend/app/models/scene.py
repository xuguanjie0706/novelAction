"""
Scene 模型 — 章节分场（三层调度核心）

每章拆分为 4-8 场（scene），每场独立规划：
- POV、时间、地点、在场角色、目标、冲突、转折、钩子、字数预算、感官焦点、节奏

这是把“AI 味平”根治的工程性关键：模型不再“展开式”写整章，而是按分场逐场写、正文 stitch、自检。

与 OutlineNode 的关系：
- 一章通常对应 1 个 OutlineNode，但可拆多个 Scene（order 1..N）
- Scene 可独立于 OutlineNode（作者手动调整分场时）
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Scene(Base):
    __tablename__ = "scenes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)  # FK → chapters.id；成稿后绑定章节
    outline_node_id = Column(UUID(as_uuid=True), ForeignKey("outline_nodes.id"), nullable=True)  # FK → outline_nodes.id，对应大纲节点

    order = Column(Integer, nullable=False)           # 场次 1..N
    title = Column(String(200))                       # 场标题（可选）

    # 时间线
    time = Column(String(100))                        # “第3日·夜” 或 “同日·上午”
    story_day = Column(String(50))                    # 故事内日期表述
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id"), nullable=True)  # FK → locations.id；由 main.py 兼容迁移补齐
    location_name = Column(String(200))               # 冗余保留，方便旧数据与 free-text 兜底

    # 视点与角色
    pov_character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=True)  # FK → characters.id，本场 POV
    characters_on_stage = Column(JSON, default=list)  # [char_id, ...] 本场在场角色

    # 戏剧元素
    goal = Column(Text)                               # 本场目标（角色想要什么）
    conflict = Column(Text)                           # 冲突/障碍
    turn = Column(Text)                               # 转折（本场发生的关键变化）
    hook = Column(Text)                               # 场末钩子（留给下一场或章末）
    hook_strength = Column(Integer, default=3)        # 1-5，钩子强度

    # 写作约束
    word_budget = Column(Integer, default=400)        # 预算字数
    actual_word_count = Column(Integer, default=0)
    pacing = Column(String(20), default="mid")        # fast / mid / slow
    sensory_focus = Column(String(30), default="mixed")  # sight / sound / smell / taste / touch / mixed

    # 状态
    status = Column(String(20), default="planned")    # planned / written / reviewed
    content = Column(Text)                            # 本场正文（写完后存）

    # ── 投料约束区（由 chapter_ingredients 服务在分场规划时写入）────
    # 本场需推进的故事线：[{storyline_id, name, line_type, from_state, to_state, must_advance}]
    storyline_moves = Column(JSON, default=None)
    # 势力/地盘着色：{faction_id, name, faction_type, alignment, atmosphere, npc_default_attitude}
    faction_color = Column(JSON, default=None)
    # 技能/法宝聚光灯：[{asset_type, asset_id, name, description, key_effect}]
    asset_spotlight = Column(JSON, default=None)
    # 伏笔操作指令：[{foreshadow_id, title, op, suggested_method, is_overdue}]
    foreshadow_ops = Column(JSON, default=None)
    # 债务标记：[{debt_type, description, severity, overdue_chapters}]
    debt_flags = Column(JSON, default=None)
    # 结构预警（规划时生成）：[{code, level, msg}]
    structural_warnings = Column(JSON, default=None)
    # 写后核验结果（stitch 后异步回填）：{storyline_ok, foreshadow_ok, debt_cleared, score, notes}
    checklist_result = Column(JSON, default=None)

    extra = Column(JSON, default=dict)  # JSON 扩展字段
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 创建时间（UTC）
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())  # 更新时间（UTC）

    project = relationship("Project", back_populates="scenes")
    chapter = relationship("Chapter", back_populates="scenes")
    outline_node = relationship("OutlineNode", back_populates="scenes")
    pov_character = relationship("Character", foreign_keys=[pov_character_id])
    location = relationship("Location", back_populates="scenes", foreign_keys=[location_id])
