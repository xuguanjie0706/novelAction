"""
ingredient_types.py — 投料清单数据类型定义

本模块定义 ChapterIngredients 及其子结构的 dataclass，
供 ingredient_compute / ingredient_prompt / 外部模块共用。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class StorylineMove:
    """单条故事线推进指令。"""
    storyline_id: str
    name: str
    line_type: str              # main/sub/romance/growth/mystery/faction/antagonist
    current_state: str          # 从 description 中提取的现阶段状态描述
    gap_chapters: int           # 距上次出现多少章（0=本章内已有）
    must_advance: bool          # 是否强制推进（超过断档阈值）
    suggested_beat: str = ""    # 建议节拍（来自 key_beats，可为空）


@dataclass
class FactionColor:
    """势力地盘着色信息。"""
    faction_id: str
    name: str
    faction_type: str
    alignment: str              # protagonist/neutral/antagonist
    atmosphere: str             # 从 description/goals 提炼的氛围描述
    npc_default_attitude: str   # 对主角的默认态度


@dataclass
class AssetCard:
    """技能或道具聚光灯卡片。"""
    asset_type: str             # "skill" or "item"
    asset_id: str
    name: str
    description: str
    visual_or_appearance: str   # 感官描述
    cost_or_rarity: str         # 消耗/稀有度
    key_effect: str             # 核心效果


@dataclass
class ForeshadowOp:
    """伏笔操作指令。"""
    foreshadow_id: str
    title: str
    op: str                     # lay / hint / resolve
    priority: int
    laid_chapter: int | None    # 埋下章节（若已知）
    suggested_method: str       # 建议处理方式
    is_overdue: bool = False    # 是否已逾期


@dataclass
class DebtFlag:
    """债务/欠账标记。"""
    debt_type: str              # payoff / storyline_gap / promise_due / emotion_debt
    description: str
    severity: str               # critical / warning / info
    overdue_chapters: int = 0
    related_id: str = ""        # 关联的 storyline_id / promise_id 等


@dataclass
class RelationshipSnapshot:
    """两个在场角色之间的关系快照。"""
    char_a_id: str
    char_a_name: str
    char_b_id: str
    char_b_name: str
    relation_type: str
    dynamic: str                # stable/evolving/deteriorating/broken
    evolution_note: str


@dataclass
class ChapterIngredients:
    """本章投料清单——写章前主动拉取的结构化约束集合。"""
    # ① 故事线推进指令
    storyline_moves: list[StorylineMove] = field(default_factory=list)
    # ② 势力/地盘着色
    faction_colors: list[FactionColor] = field(default_factory=list)
    # ③ 技能/法宝聚光灯
    asset_spotlight: list[AssetCard] = field(default_factory=list)
    # ④ 伏笔操作指令
    foreshadow_ops: list[ForeshadowOp] = field(default_factory=list)
    # ⑤ 债务标记
    debt_flags: list[DebtFlag] = field(default_factory=list)
    # ⑥ 人物关系快照（在场角色两两之间）
    relationship_snapshots: list[RelationshipSnapshot] = field(default_factory=list)
    # ⑦ 反派幕后动态
    villain_offscreen: str = ""
    # ⑧ 情绪预算
    emotional_quota: dict = field(default_factory=dict)
    # ⑨ 世界规则（场景相关的 WorldSetting 卡片摘要）
    world_rules: list[str] = field(default_factory=list)
    # ⑩ 故事线织网约束文本块（分场 path，与整章 storyline_summary 对齐）
    storyline_weave_block: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
