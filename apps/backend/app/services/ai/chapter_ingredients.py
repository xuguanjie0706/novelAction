"""
chapter_ingredients.py — 本章投料清单计算服务

设计动机：Bootstrap 生成了丰富设定，但写章时这些数据是「被动词典」。
本模块在写章前主动从所有设定表拉取与本章相关的约束，输出结构化
ChapterIngredients 对象，供分场规划 + 逐场起草注入使用。

核心特性：
- 纯 DB 查询，不调用 LLM，速度快（< 500ms）
- 计算欠账债务（故事线断档 / 爽点欠债 / 伏笔到期 / 承诺临期）
- 结果持久化到 OutlineNode.extra.pre_write_constraints
- 同时服务于「写前预警面板展示」和「分场 AI 约束注入」

约束计算阈值（均可在 THRESHOLDS 调整）：
- STORYLINE_GAP_THRESHOLD: 故事线断档超此章数 → MUST_ADVANCE
- PAYOFF_DEBT_THRESHOLD: 爽点欠债超此章数 → MUST_PAYOFF
- FORESHADOW_HINT_THRESHOLD: 伏笔悬置超此章数 → 应 hint
- PROMISE_DUE_CHAPTERS: 承诺还有这么多章到期 → 标记临期
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── 可调阈值 ──────────────────────────────────────────────────────
THRESHOLDS = {
    "STORYLINE_GAP": 5,         # 故事线断档超过 N 章 → MUST_ADVANCE
    "PAYOFF_DEBT": 3,           # 爽点欠债超过 N 章 → MUST_PAYOFF
    "FORESHADOW_HINT": 10,      # 伏笔悬置超过 N 章 → 应 hint
    "FORESHADOW_RESOLVE": 20,   # 伏笔悬置超过 N 章 → 应 resolve
    "PROMISE_DUE_CHAPTERS": 3,  # 承诺还有 N 章窗口结束 → 临期警告
}


# ── 数据类：投料清单各字段 ────────────────────────────────────────

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

    def to_dict(self) -> dict:
        return asdict(self)


# ── 主入口 ────────────────────────────────────────────────────────

async def compute_chapter_ingredients(
    db: Session,
    project_id: str,
    outline_node_id: str,
    chapter_number: int = 0,
) -> ChapterIngredients:
    """
    主动从所有设定表拉取与本章相关的约束，返回 ChapterIngredients。

    Args:
        db: SQLAlchemy Session
        project_id: 项目 UUID 字符串
        outline_node_id: 章节大纲节点 UUID 字符串
        chapter_number: 当前章节序号（用于计算断档/欠债章数）

    Returns:
        ChapterIngredients 结构化对象（同时将 to_dict() 写入
        OutlineNode.extra.pre_write_constraints）

    Notes:
        纯 DB 查询，不调用 LLM，速度快。
    """
    from app.models import (
        Character, CharacterRelationship, Faction, Foreshadow,
        Item, OutlineNode, Project, ReaderPromise, Skill, StoryLine,
    )

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        logger.warning("compute_chapter_ingredients: project %s not found", project_id)
        return ChapterIngredients()

    node = db.query(OutlineNode).filter(
        OutlineNode.id == outline_node_id,
        OutlineNode.project_id == project_id,
    ).first()
    if not node:
        logger.warning("compute_chapter_ingredients: node %s not found", outline_node_id)
        return ChapterIngredients()

    # 使用节点的章节序号（若未传入）
    if not chapter_number and node.sort_order:
        chapter_number = node.sort_order

    ingredients = ChapterIngredients()

    # ① 故事线推进指令
    ingredients.storyline_moves = await _compute_storyline_moves(
        db, project_id, node, chapter_number
    )

    # ② 势力着色（取在场角色所属势力 + 主角所在势力）
    ingredients.faction_colors = _compute_faction_colors(
        db, project_id, node
    )

    # ③ 技能/法宝聚光灯（仅本章 key_skill_ids / key_item_ids）
    ingredients.asset_spotlight = _compute_asset_spotlight(
        db, project_id, node
    )

    # ④ 伏笔操作指令
    ingredients.foreshadow_ops = _compute_foreshadow_ops(
        db, project_id, node, chapter_number
    )

    # ⑤ 债务标记（综合计算）
    ingredients.debt_flags = _compute_debt_flags(
        db, project_id, project, node,
        ingredients.storyline_moves, chapter_number
    )

    # ⑥ 人物关系快照（在场角色两两之间）
    ingredients.relationship_snapshots = _compute_relationship_snapshots(
        db, project_id, node
    )

    # ⑦ 反派幕后动态（从 villain_arc 提取当前卷对应条目）
    ingredients.villain_offscreen = _extract_villain_offscreen(project, node, db)

    # ⑧ 情绪预算（从 emotion_arc 提取）
    ingredients.emotional_quota = _extract_emotional_quota(project, node)

    # 持久化到 OutlineNode.extra
    _persist_to_node(db, node, ingredients)

    return ingredients


# ── 子计算函数 ────────────────────────────────────────────────────

async def _compute_storyline_moves(
    db: Session,
    project_id: str,
    node,
    chapter_number: int,
) -> list[StorylineMove]:
    """
    计算本章需推进的故事线及推进指令。

    逻辑：
    1. 从 node.storyline_ids 取本章关联故事线
    2. 对每条线，扫描其他 OutlineNode.storyline_ids 找最近一次出现章号
    3. 断档 > STORYLINE_GAP_THRESHOLD 的线标记 must_advance=True
    """
    from app.models import OutlineNode, StoryLine

    storyline_ids = node.storyline_ids or []
    if not storyline_ids:
        # 没有明确绑定时，取 status=active 的前 3 条主线/感情线
        active_lines = db.query(StoryLine).filter(
            StoryLine.project_id == project_id,
            StoryLine.status.in_(["active", "planned"]),
            StoryLine.line_type.in_(["main", "romance", "antagonist"]),
        ).order_by(StoryLine.sort_order.asc()).limit(3).all()
        storyline_ids = [str(sl.id) for sl in active_lines]

    if not storyline_ids:
        return []

    lines = db.query(StoryLine).filter(
        StoryLine.id.in_(storyline_ids),
        StoryLine.project_id == project_id,
    ).all()

    # 查询每条线最近一次出现在哪个章节节点（sort_order 最大的）
    all_chapter_nodes = db.query(
        OutlineNode.id,
        OutlineNode.sort_order,
        OutlineNode.storyline_ids,
    ).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
        OutlineNode.sort_order < chapter_number,  # 只看之前章节
    ).all()

    result: list[StorylineMove] = []
    threshold = THRESHOLDS["STORYLINE_GAP"]

    for line in lines:
        sid = str(line.id)
        # 找到包含此故事线 ID 的最近章节
        last_chapter = 0
        for n in all_chapter_nodes:
            n_storyline_ids = n.storyline_ids or []
            # storyline_ids 可能存的是 UUID 对象或字符串
            n_sids = [str(x) for x in n_storyline_ids]
            if sid in n_sids and (n.sort_order or 0) > last_chapter:
                last_chapter = n.sort_order or 0

        gap = chapter_number - last_chapter if last_chapter > 0 else 999
        must_advance = gap > threshold

        # 从 key_beats 提取下一个建议节拍
        suggested_beat = ""
        if line.key_beats:
            for beat in line.key_beats:
                if isinstance(beat, dict):
                    ch_range = beat.get("chapter_range", "")
                    milestone = beat.get("milestone", "") or beat.get("beat", "")
                    # 找到 chapter_number 落在范围内的节拍
                    if milestone and _chapter_in_range(chapter_number, ch_range):
                        suggested_beat = milestone
                        break

        result.append(StorylineMove(
            storyline_id=sid,
            name=line.name,
            line_type=line.line_type or "main",
            current_state=(line.description or "")[:150],
            gap_chapters=gap if last_chapter > 0 else 0,
            must_advance=must_advance,
            suggested_beat=suggested_beat,
        ))

    # 优先排 must_advance=True 的
    result.sort(key=lambda x: (not x.must_advance, x.gap_chapters * -1))
    return result[:5]  # 最多 5 条


def _compute_faction_colors(
    db: Session,
    project_id: str,
    node,
) -> list[FactionColor]:
    """
    计算本章涉及的势力着色信息。

    策略：
    1. 取 node.involved_character_ids 的角色所属势力
    2. 合并去重
    3. 最多返回 3 个势力
    """
    from app.models import Character, Faction

    char_ids = node.involved_character_ids or []
    if not char_ids:
        return []

    chars = db.query(Character).filter(
        Character.id.in_(char_ids),
        Character.project_id == project_id,
        Character.faction_id.isnot(None),
    ).limit(10).all()

    faction_ids = list({str(c.faction_id) for c in chars if c.faction_id})
    if not faction_ids:
        return []

    factions = db.query(Faction).filter(
        Faction.id.in_(faction_ids),
        Faction.project_id == project_id,
    ).all()

    result: list[FactionColor] = []
    for f in factions[:3]:
        # 从 description/goals 提炼氛围（取前 80 字）
        atmosphere = ""
        if f.description:
            atmosphere = f.description[:80]
        elif f.goals:
            atmosphere = f.goals[:80]

        # 对主角的态度
        attitude_map = {
            "friendly": "友善",
            "hostile": "敌视",
            "neutral": "冷漠",
            "subordinate": "支配（主角下级）",
            "superior": "压制（主角上级）",
        }
        npc_attitude = attitude_map.get(
            f.attitude_to_protagonist or "neutral", "中立冷漠"
        )

        result.append(FactionColor(
            faction_id=str(f.id),
            name=f.name,
            faction_type=f.faction_type or "sect",
            alignment=f.alignment or "neutral",
            atmosphere=atmosphere,
            npc_default_attitude=npc_attitude,
        ))

    return result


def _compute_asset_spotlight(
    db: Session,
    project_id: str,
    node,
) -> list[AssetCard]:
    """
    计算本章技能/法宝聚光灯。

    从 node.key_skill_ids + node.key_item_ids 拉取卡片信息。
    """
    from app.models import Item, Skill

    cards: list[AssetCard] = []

    # 技能
    skill_ids = node.key_skill_ids or []
    if skill_ids:
        skills = db.query(Skill).filter(
            Skill.id.in_(skill_ids),
            Skill.project_id == project_id,
        ).limit(4).all()
        for sk in skills:
            cards.append(AssetCard(
                asset_type="skill",
                asset_id=str(sk.id),
                name=sk.name,
                description=(sk.description or "")[:120],
                visual_or_appearance="",  # Skill 无独立外观字段，从 description 取
                cost_or_rarity="",
                key_effect=(sk.effects or "")[:100],
            ))

    # 道具
    item_ids = node.key_item_ids or []
    if item_ids:
        items = db.query(Item).filter(
            Item.id.in_(item_ids),
            Item.project_id == project_id,
        ).limit(4).all()
        for it in items:
            cards.append(AssetCard(
                asset_type="item",
                asset_id=str(it.id),
                name=it.name,
                description=(it.description or "")[:120],
                visual_or_appearance="",
                cost_or_rarity=it.rarity or "rare",
                key_effect=(it.description or "")[:80],
            ))

    return cards


def _compute_foreshadow_ops(
    db: Session,
    project_id: str,
    node,
    chapter_number: int,
) -> list[ForeshadowOp]:
    """
    计算本章伏笔操作指令。

    优先级：
    1. node.foreshadows_resolved → op=resolve（本章明确要回收）
    2. node.foreshadows_laid → op=lay（本章明确要埋）
    3. 超过 FORESHADOW_RESOLVE_THRESHOLD → op=resolve（强制回收）
    4. 超过 FORESHADOW_HINT_THRESHOLD → op=hint（应 hint）
    最多返回 5 条
    """
    from app.models import Foreshadow

    ops: list[ForeshadowOp] = []
    seen_ids: set[str] = set()

    # ① 明确要回收的伏笔
    for fw_ref in (node.foreshadows_resolved or []):
        fw_id = fw_ref.get("id") or fw_ref.get("foreshadow_id") or ""
        if not fw_id or fw_id in seen_ids:
            continue
        fw = db.query(Foreshadow).filter(
            Foreshadow.id == fw_id, Foreshadow.project_id == project_id
        ).first()
        if fw:
            ops.append(ForeshadowOp(
                foreshadow_id=str(fw.id),
                title=fw.title or "",
                op="resolve",
                priority=fw.priority or 3,
                laid_chapter=fw.planted_chapter,
                suggested_method=f"本章明确规划回收：{fw_ref.get('description', '')}",
            ))
            seen_ids.add(str(fw.id))

    # ② 明确要埋的伏笔
    for fw_ref in (node.foreshadows_laid or []):
        fw_id = fw_ref.get("id") or fw_ref.get("foreshadow_id") or ""
        if not fw_id or fw_id in seen_ids:
            continue
        fw = db.query(Foreshadow).filter(
            Foreshadow.id == fw_id, Foreshadow.project_id == project_id
        ).first()
        if fw:
            ops.append(ForeshadowOp(
                foreshadow_id=str(fw.id),
                title=fw.title or "",
                op="lay",
                priority=fw.priority or 3,
                laid_chapter=None,
                suggested_method=f"本章规划埋下：{fw_ref.get('description', '')}",
            ))
            seen_ids.add(str(fw.id))

    # ③ 自动检测过期/应 hint 的伏笔（优先级 ≥ 3，状态 open）
    hint_threshold = THRESHOLDS["FORESHADOW_HINT"]
    resolve_threshold = THRESHOLDS["FORESHADOW_RESOLVE"]

    open_fws = db.query(Foreshadow).filter(
        Foreshadow.project_id == project_id,
        Foreshadow.status == "open",
        Foreshadow.priority >= 3,
    ).order_by(Foreshadow.priority.desc()).limit(20).all()

    for fw in open_fws:
        fid = str(fw.id)
        if fid in seen_ids:
            continue
        planted = fw.planted_chapter or 0
        if planted == 0:
            continue
        age = chapter_number - planted
        is_overdue = fw.planned_resolve_chapter and chapter_number >= fw.planned_resolve_chapter

        if age >= resolve_threshold or is_overdue:
            ops.append(ForeshadowOp(
                foreshadow_id=fid,
                title=fw.title or "",
                op="resolve",
                priority=fw.priority or 3,
                laid_chapter=planted,
                suggested_method="已悬置过久，本章应回收或给出重要线索",
                is_overdue=bool(is_overdue),
            ))
            seen_ids.add(fid)
        elif age >= hint_threshold:
            ops.append(ForeshadowOp(
                foreshadow_id=fid,
                title=fw.title or "",
                op="hint",
                priority=fw.priority or 3,
                laid_chapter=planted,
                suggested_method="已悬置较久，本章可自然提及或给读者线索",
                is_overdue=False,
            ))
            seen_ids.add(fid)

        if len(ops) >= 5:
            break

    return ops[:5]


def _compute_debt_flags(
    db: Session,
    project_id: str,
    project,
    node,
    storyline_moves: list[StorylineMove],
    chapter_number: int,
) -> list[DebtFlag]:
    """
    综合计算本章的债务标记。

    包含：爽点欠账 / 故事线断档 / 承诺临期
    """
    from app.models import ReaderPromise

    flags: list[DebtFlag] = []
    extra = project.extra or {}

    # ① 爽点欠债
    ledger = extra.get("payoff_ledger", {})
    payoff_debt = ledger.get("payoff_debt", 0)
    pending_setups = ledger.get("pending_setups", [])
    if payoff_debt >= THRESHOLDS["PAYOFF_DEBT"] and pending_setups:
        setup_desc = "、".join(
            s.get("desc", "") for s in pending_setups[:2] if s.get("desc")
        )
        flags.append(DebtFlag(
            debt_type="payoff",
            description=f"爽点已欠 {payoff_debt} 章。可兑现的「因」：{setup_desc}",
            severity="critical",
            overdue_chapters=payoff_debt,
        ))

    # ② 故事线断档（从 storyline_moves 直接读）
    for move in storyline_moves:
        if move.must_advance and move.gap_chapters > THRESHOLDS["STORYLINE_GAP"]:
            flags.append(DebtFlag(
                debt_type="storyline_gap",
                description=f"「{move.name}」（{move.line_type}）已断档 {move.gap_chapters} 章",
                severity="critical" if move.gap_chapters > 8 else "warning",
                overdue_chapters=move.gap_chapters,
                related_id=move.storyline_id,
            ))

    # ③ 读者承诺临期
    due_promises = db.query(ReaderPromise).filter(
        ReaderPromise.project_id == project_id,
        ReaderPromise.status == "open",
        ReaderPromise.priority >= 3,
    ).all()
    for rp in due_promises:
        window = rp.expected_chapter_window or []
        if isinstance(window, list) and len(window) == 2:
            _, end_ch = window
            if isinstance(end_ch, int) and 0 < end_ch - chapter_number <= THRESHOLDS["PROMISE_DUE_CHAPTERS"]:
                flags.append(DebtFlag(
                    debt_type="promise_due",
                    description=f"承诺「{(rp.promise_text or '')[:60]}」还有 {end_ch - chapter_number} 章到期",
                    severity="warning",
                    overdue_chapters=0,
                    related_id=str(rp.id),
                ))

    return flags


def _compute_relationship_snapshots(
    db: Session,
    project_id: str,
    node,
) -> list[RelationshipSnapshot]:
    """
    计算本章在场角色两两之间的关系快照。

    只取 involved_character_ids 列出的角色，两两组合查关系表。
    """
    from app.models import Character, CharacterRelationship

    char_ids = [str(cid) for cid in (node.involved_character_ids or [])]
    if len(char_ids) < 2:
        return []

    # 取角色名
    chars = db.query(Character).filter(
        Character.id.in_(char_ids[:8]),
        Character.project_id == project_id,
    ).all()
    char_name_map = {str(c.id): c.name for c in chars}

    # 查询两两关系
    rels = db.query(CharacterRelationship).filter(
        CharacterRelationship.project_id == project_id,
        CharacterRelationship.from_character_id.in_(char_ids[:8]),
        CharacterRelationship.to_character_id.in_(char_ids[:8]),
    ).limit(10).all()

    result: list[RelationshipSnapshot] = []
    for rel in rels:
        a_id = str(rel.from_character_id)
        b_id = str(rel.to_character_id)
        result.append(RelationshipSnapshot(
            char_a_id=a_id,
            char_a_name=char_name_map.get(a_id, "?"),
            char_b_id=b_id,
            char_b_name=char_name_map.get(b_id, "?"),
            relation_type=rel.relation_type or "未知",
            dynamic=rel.is_dynamic or "stable",
            evolution_note=(rel.evolution_note or "")[:200],
        ))

    return result[:6]


def _extract_villain_offscreen(project, node, db: Session) -> str:
    """从 Project.extra.villain_arc 提取当前卷的反派幕后动态。"""
    extra = project.extra or {}
    villain_arc = extra.get("villain_arc", {})
    if not villain_arc:
        return ""

    # 找当前卷号（从 node 向上找 volume 节点）
    vol_index = 0
    if node.parent_id:
        from app.models import OutlineNode
        parent = db.query(OutlineNode).filter(OutlineNode.id == node.parent_id).first()
        if parent and parent.sort_order:
            vol_index = (parent.sort_order or 1) - 1

    arcs = villain_arc.get("volumes") or villain_arc.get("arcs") or []
    if isinstance(arcs, list) and vol_index < len(arcs):
        vol_arc = arcs[vol_index]
        if isinstance(vol_arc, dict):
            return vol_arc.get("action", "") or vol_arc.get("description", "") or str(vol_arc)[:200]
        return str(vol_arc)[:200]

    # 降级：返回顶层描述
    return (villain_arc.get("description") or villain_arc.get("summary") or "")[:200]


def _extract_emotional_quota(project, node) -> dict:
    """从 Project.extra.emotion_arc 提取当前卷/阶段的情绪预算。"""
    extra = project.extra or {}
    emotion_arc = extra.get("emotion_arc", {})
    if not emotion_arc:
        return {}

    # 当前卷情绪色调
    volumes = emotion_arc.get("volumes") or []
    if isinstance(volumes, list) and volumes:
        vol_idx = 0
        if node.parent_id:
            # 用 sort_order 对应卷 index（简单近似）
            vol_idx = max(0, (node.sort_order or 1) // 10)
        if vol_idx < len(volumes):
            return volumes[vol_idx] if isinstance(volumes[vol_idx], dict) else {}

    return {
        "volume_tone": emotion_arc.get("primary_tone", ""),
        "budget": emotion_arc.get("net_balance", ""),
        "forbidden_tone": emotion_arc.get("forbidden_tone", ""),
    }


def _persist_to_node(db: Session, node, ingredients: ChapterIngredients) -> None:
    """将计算结果序列化并写入 OutlineNode.extra.pre_write_constraints。"""
    try:
        import datetime
        extra = dict(node.extra or {})
        extra["pre_write_constraints"] = {
            "computed_at": datetime.datetime.utcnow().isoformat(),
            **ingredients.to_dict(),
        }
        node.extra = extra
        db.commit()
    except Exception as exc:
        logger.warning("persist_to_node failed: %s", exc)
        db.rollback()


# ── 工具函数 ──────────────────────────────────────────────────────

def _chapter_in_range(chapter_number: int, ch_range: Any) -> bool:
    """判断 chapter_number 是否在 ch_range 描述的范围内。"""
    if not ch_range:
        return False
    if isinstance(ch_range, (list, tuple)) and len(ch_range) == 2:
        try:
            return int(ch_range[0]) <= chapter_number <= int(ch_range[1])
        except (ValueError, TypeError):
            return False
    if isinstance(ch_range, str):
        import re
        m = re.match(r"(\d+)\s*[-–]\s*(\d+)", ch_range)
        if m:
            return int(m.group(1)) <= chapter_number <= int(m.group(2))
    return False


def build_constraints_prompt_block(ingredients: ChapterIngredients) -> str:
    """
    将 ChapterIngredients 格式化为可注入分场/起草 prompt 的约束文本块。

    供 scene_routes.py 的 scene_plan_save 和 scene_draft_stream 使用。
    """
    parts: list[str] = []

    # 故事线推进任务
    must_moves = [m for m in ingredients.storyline_moves if m.must_advance]
    optional_moves = [m for m in ingredients.storyline_moves if not m.must_advance]
    if must_moves or optional_moves:
        lines = []
        for m in must_moves:
            beat = f"→ 建议节拍：{m.suggested_beat}" if m.suggested_beat else ""
            lines.append(
                f"  [MUST] 「{m.name}」（{m.line_type}）"
                f"已断档 {m.gap_chapters} 章，本章必须推进。{beat}"
            )
        for m in optional_moves[:2]:
            lines.append(f"  [可选] 「{m.name}」（{m.line_type}）")
        parts.append("【故事线推进任务】\n" + "\n".join(lines))

    # 债务偿还
    critical_debts = [d for d in ingredients.debt_flags if d.severity == "critical"]
    warn_debts = [d for d in ingredients.debt_flags if d.severity == "warning"]
    if critical_debts or warn_debts:
        lines = []
        for d in critical_debts:
            lines.append(f"  🔴 [MUST] {d.description}")
        for d in warn_debts:
            lines.append(f"  🟡 [警告] {d.description}")
        parts.append("【本章必须偿还的债务】\n" + "\n".join(lines))

    # 伏笔操作
    if ingredients.foreshadow_ops:
        lines = []
        for op in ingredients.foreshadow_ops:
            overdue_tag = "【逾期】" if op.is_overdue else ""
            lines.append(
                f"  {op.op.upper()} {overdue_tag}「{op.title}」：{op.suggested_method}"
            )
        parts.append("【伏笔操作】\n" + "\n".join(lines))

    # 势力地盘着色
    if ingredients.faction_colors:
        lines = []
        for fc in ingredients.faction_colors:
            lines.append(
                f"  「{fc.name}」（{fc.faction_type}/{fc.alignment}）"
                f"氛围：{fc.atmosphere[:60]}；NPC 态度：{fc.npc_default_attitude}"
            )
        parts.append("【势力/地盘着色】\n" + "\n".join(lines))

    # 技能/法宝聚光灯
    if ingredients.asset_spotlight:
        lines = []
        for a in ingredients.asset_spotlight:
            effect = a.key_effect[:60] if a.key_effect else a.description[:60]
            lines.append(f"  【{a.name}】{effect}")
        parts.append("【本章技能/法宝聚光灯】\n" + "\n".join(lines))

    # 人物关系快照
    if ingredients.relationship_snapshots:
        lines = []
        for snap in ingredients.relationship_snapshots[:3]:
            lines.append(
                f"  {snap.char_a_name} ↔ {snap.char_b_name}："
                f"{snap.relation_type}（{snap.dynamic}）{snap.evolution_note[:60]}"
            )
        parts.append("【在场角色关系快照】\n" + "\n".join(lines))

    # 反派幕后动态
    if ingredients.villain_offscreen:
        parts.append(f"【反派幕后动态】\n  {ingredients.villain_offscreen[:200]}")

    # 情绪预算
    if ingredients.emotional_quota:
        quota = ingredients.emotional_quota
        tone = quota.get("volume_tone") or quota.get("primary_tone") or ""
        forbidden = quota.get("forbidden_tone") or ""
        if tone or forbidden:
            lines = []
            if tone:
                lines.append(f"  卷级基调：{tone}")
            if forbidden:
                lines.append(f"  禁止情绪：{forbidden}")
            parts.append("【情绪预算】\n" + "\n".join(lines))

    if not parts:
        return ""

    return (
        "\n\n===【本章投料约束（由系统主动计算，分场时必须分配落实）】===\n"
        + "\n\n".join(parts)
        + "\n===【约束结束】==="
    )
