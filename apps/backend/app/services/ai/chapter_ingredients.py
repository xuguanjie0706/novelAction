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

拆分结构：
  - ingredient_types.py: 数据类型定义（dataclass）
  - ingredient_prompt.py: prompt 格式化（build_constraints_prompt_block）
  - 本文件: 计算逻辑 + re-export

约束计算阈值（均可在 THRESHOLDS 调整）：
- STORYLINE_GAP_THRESHOLD: 故事线断档超此章数 → MUST_ADVANCE
- PAYOFF_DEBT_THRESHOLD: 爽点欠债超此章数 → MUST_PAYOFF
- FORESHADOW_HINT_THRESHOLD: 伏笔悬置超此章数 → 应 hint
- PROMISE_DUE_CHAPTERS: 承诺还有这么多章到期 → 标记临期
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

# ── re-export：保持外部 import 路径不变 ──────────────────────────
from app.services.ai.ingredient_types import (  # noqa: F401
    AssetCard,
    ChapterIngredients,
    DebtFlag,
    FactionColor,
    ForeshadowOp,
    RelationshipSnapshot,
    StorylineMove,
)
from app.services.ai.ingredient_prompt import build_constraints_prompt_block  # noqa: F401

logger = logging.getLogger(__name__)

# ── 可调阈值 ──────────────────────────────────────────────────────
THRESHOLDS = {
    "STORYLINE_GAP": 5,
    "PAYOFF_DEBT": 3,
    "FORESHADOW_HINT": 10,
    "FORESHADOW_RESOLVE": 20,
    "PROMISE_DUE_CHAPTERS": 3,
}


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
    from app.models import OutlineNode, Project

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

    if not chapter_number and node.sort_order:
        chapter_number = node.sort_order

    ingredients = ChapterIngredients()
    ingredients.storyline_moves = await _compute_storyline_moves(db, project_id, node, chapter_number)
    ingredients.faction_colors = _compute_faction_colors(db, project_id, node)
    ingredients.asset_spotlight = _compute_asset_spotlight(db, project_id, node)
    ingredients.foreshadow_ops = _compute_foreshadow_ops(db, project_id, node, chapter_number)
    ingredients.debt_flags = _compute_debt_flags(
        db, project_id, project, node, ingredients.storyline_moves, chapter_number
    )
    ingredients.relationship_snapshots = _compute_relationship_snapshots(db, project_id, node)
    ingredients.villain_offscreen = _extract_villain_offscreen(project, node, db)
    ingredients.emotional_quota = _extract_emotional_quota(project, node)
    _persist_to_node(db, node, ingredients)

    return ingredients


# ── 子计算函数 ────────────────────────────────────────────────────

async def _compute_storyline_moves(
    db: Session, project_id: str, node, chapter_number: int,
) -> list[StorylineMove]:
    """计算本章需推进的故事线及推进指令。"""
    from app.models import OutlineNode, StoryLine

    storyline_ids = node.storyline_ids or []
    if not storyline_ids:
        active_lines = db.query(StoryLine).filter(
            StoryLine.project_id == project_id,
            StoryLine.status.in_(["active", "planned"]),
            StoryLine.line_type.in_(["main", "romance", "antagonist"]),
        ).order_by(StoryLine.sort_order.asc()).limit(3).all()
        storyline_ids = [str(sl.id) for sl in active_lines]

    if not storyline_ids:
        return []

    lines = db.query(StoryLine).filter(
        StoryLine.id.in_(storyline_ids), StoryLine.project_id == project_id,
    ).all()

    all_chapter_nodes = db.query(
        OutlineNode.id, OutlineNode.sort_order, OutlineNode.storyline_ids,
    ).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
        OutlineNode.sort_order < chapter_number,
    ).all()

    result: list[StorylineMove] = []
    threshold = THRESHOLDS["STORYLINE_GAP"]

    for line in lines:
        sid = str(line.id)
        last_chapter = 0
        for n in all_chapter_nodes:
            n_sids = [str(x) for x in (n.storyline_ids or [])]
            if sid in n_sids and (n.sort_order or 0) > last_chapter:
                last_chapter = n.sort_order or 0

        gap = chapter_number - last_chapter if last_chapter > 0 else 999
        must_advance = gap > threshold

        suggested_beat = ""
        if line.key_beats:
            for beat in line.key_beats:
                if isinstance(beat, dict):
                    ch_range = beat.get("chapter_range", "")
                    milestone = beat.get("milestone", "") or beat.get("beat", "")
                    if milestone and _chapter_in_range(chapter_number, ch_range):
                        suggested_beat = milestone
                        break

        result.append(StorylineMove(
            storyline_id=sid, name=line.name,
            line_type=line.line_type or "main",
            current_state=(line.description or "")[:150],
            gap_chapters=gap if last_chapter > 0 else 0,
            must_advance=must_advance, suggested_beat=suggested_beat,
        ))

    result.sort(key=lambda x: (not x.must_advance, x.gap_chapters * -1))
    return result[:5]


def _compute_faction_colors(db: Session, project_id: str, node) -> list[FactionColor]:
    """计算本章涉及的势力着色信息。"""
    from app.models import Character, Faction

    char_ids = node.involved_character_ids or []
    if not char_ids:
        return []

    chars = db.query(Character).filter(
        Character.id.in_(char_ids), Character.project_id == project_id,
        Character.faction_id.isnot(None),
    ).limit(10).all()

    faction_ids = list({str(c.faction_id) for c in chars if c.faction_id})
    if not faction_ids:
        return []

    factions = db.query(Faction).filter(
        Faction.id.in_(faction_ids), Faction.project_id == project_id,
    ).all()

    attitude_map = {
        "friendly": "友善", "hostile": "敌视", "neutral": "冷漠",
        "subordinate": "支配（主角下级）", "superior": "压制（主角上级）",
    }

    result: list[FactionColor] = []
    for f in factions[:3]:
        atmosphere = ""
        if f.description:
            atmosphere = f.description[:80]
        elif f.goals:
            atmosphere = f.goals[:80]

        result.append(FactionColor(
            faction_id=str(f.id), name=f.name,
            faction_type=f.faction_type or "sect",
            alignment=f.alignment or "neutral",
            atmosphere=atmosphere,
            npc_default_attitude=attitude_map.get(f.attitude_to_protagonist or "neutral", "中立冷漠"),
        ))
    return result


def _compute_asset_spotlight(db: Session, project_id: str, node) -> list[AssetCard]:
    """计算本章技能/法宝聚光灯。"""
    from app.models import Item, Skill

    cards: list[AssetCard] = []
    skill_ids = node.key_skill_ids or []
    if skill_ids:
        skills = db.query(Skill).filter(
            Skill.id.in_(skill_ids), Skill.project_id == project_id,
        ).limit(4).all()
        for sk in skills:
            cards.append(AssetCard(
                asset_type="skill", asset_id=str(sk.id), name=sk.name,
                description=(sk.description or "")[:120],
                visual_or_appearance="", cost_or_rarity="",
                key_effect=(sk.effects or "")[:100],
            ))

    item_ids = node.key_item_ids or []
    if item_ids:
        items = db.query(Item).filter(
            Item.id.in_(item_ids), Item.project_id == project_id,
        ).limit(4).all()
        for it in items:
            cards.append(AssetCard(
                asset_type="item", asset_id=str(it.id), name=it.name,
                description=(it.description or "")[:120],
                visual_or_appearance="", cost_or_rarity=it.rarity or "rare",
                key_effect=(it.description or "")[:80],
            ))
    return cards


def _compute_foreshadow_ops(
    db: Session, project_id: str, node, chapter_number: int,
) -> list[ForeshadowOp]:
    """计算本章伏笔操作指令。"""
    from app.models import Foreshadow

    ops: list[ForeshadowOp] = []
    seen_ids: set[str] = set()

    for fw_ref in (node.foreshadows_resolved or []):
        fw_id = fw_ref.get("id") or fw_ref.get("foreshadow_id") or ""
        if not fw_id or fw_id in seen_ids:
            continue
        fw = db.query(Foreshadow).filter(
            Foreshadow.id == fw_id, Foreshadow.project_id == project_id
        ).first()
        if fw:
            ops.append(ForeshadowOp(
                foreshadow_id=str(fw.id), title=fw.title or "", op="resolve",
                priority=fw.priority or 3, laid_chapter=fw.laid_chapter_number,
                suggested_method=f"本章明确规划回收：{fw_ref.get('description', '')}",
            ))
            seen_ids.add(str(fw.id))

    for fw_ref in (node.foreshadows_laid or []):
        fw_id = fw_ref.get("id") or fw_ref.get("foreshadow_id") or ""
        if not fw_id or fw_id in seen_ids:
            continue
        fw = db.query(Foreshadow).filter(
            Foreshadow.id == fw_id, Foreshadow.project_id == project_id
        ).first()
        if fw:
            ops.append(ForeshadowOp(
                foreshadow_id=str(fw.id), title=fw.title or "", op="lay",
                priority=fw.priority or 3, laid_chapter=None,
                suggested_method=f"本章规划埋下：{fw_ref.get('description', '')}",
            ))
            seen_ids.add(str(fw.id))

    hint_threshold = THRESHOLDS["FORESHADOW_HINT"]
    resolve_threshold = THRESHOLDS["FORESHADOW_RESOLVE"]

    open_fws = db.query(Foreshadow).filter(
        Foreshadow.project_id == project_id,
        Foreshadow.status == "open", Foreshadow.priority >= 3,
    ).order_by(Foreshadow.priority.desc()).limit(20).all()

    for fw in open_fws:
        fid = str(fw.id)
        if fid in seen_ids:
            continue
        planted = fw.laid_chapter_number or 0
        if planted == 0:
            continue
        age = chapter_number - planted
        is_overdue = fw.planned_resolve_chapter and chapter_number >= fw.planned_resolve_chapter

        if age >= resolve_threshold or is_overdue:
            ops.append(ForeshadowOp(
                foreshadow_id=fid, title=fw.title or "", op="resolve",
                priority=fw.priority or 3, laid_chapter=planted,
                suggested_method="已悬置过久，本章应回收或给出重要线索",
                is_overdue=bool(is_overdue),
            ))
            seen_ids.add(fid)
        elif age >= hint_threshold:
            ops.append(ForeshadowOp(
                foreshadow_id=fid, title=fw.title or "", op="hint",
                priority=fw.priority or 3, laid_chapter=planted,
                suggested_method="已悬置较久，本章可自然提及或给读者线索",
            ))
            seen_ids.add(fid)

        if len(ops) >= 5:
            break

    return ops[:5]


def _compute_debt_flags(
    db: Session, project_id: str, project, node,
    storyline_moves: list[StorylineMove], chapter_number: int,
) -> list[DebtFlag]:
    """综合计算本章的债务标记。"""
    from app.models import ReaderPromise

    flags: list[DebtFlag] = []
    extra = project.extra or {}

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
            severity="critical", overdue_chapters=payoff_debt,
        ))

    for move in storyline_moves:
        if move.must_advance and move.gap_chapters > THRESHOLDS["STORYLINE_GAP"]:
            flags.append(DebtFlag(
                debt_type="storyline_gap",
                description=f"「{move.name}」（{move.line_type}）已断档 {move.gap_chapters} 章",
                severity="critical" if move.gap_chapters > 8 else "warning",
                overdue_chapters=move.gap_chapters, related_id=move.storyline_id,
            ))

    due_promises = db.query(ReaderPromise).filter(
        ReaderPromise.project_id == project_id,
        ReaderPromise.status == "open", ReaderPromise.priority >= 3,
    ).all()
    for rp in due_promises:
        window = rp.expected_chapter_window or []
        if isinstance(window, list) and len(window) == 2:
            _, end_ch = window
            if isinstance(end_ch, int) and 0 < end_ch - chapter_number <= THRESHOLDS["PROMISE_DUE_CHAPTERS"]:
                flags.append(DebtFlag(
                    debt_type="promise_due",
                    description=f"承诺「{(rp.promise_text or '')[:60]}」还有 {end_ch - chapter_number} 章到期",
                    severity="warning", related_id=str(rp.id),
                ))

    return flags


def _compute_relationship_snapshots(
    db: Session, project_id: str, node,
) -> list[RelationshipSnapshot]:
    """计算本章在场角色两两之间的关系快照。"""
    from app.models import Character, CharacterRelationship

    char_ids = [str(cid) for cid in (node.involved_character_ids or [])]
    if len(char_ids) < 2:
        return []

    chars = db.query(Character).filter(
        Character.id.in_(char_ids[:8]), Character.project_id == project_id,
    ).all()
    char_name_map = {str(c.id): c.name for c in chars}

    rels = db.query(CharacterRelationship).filter(
        CharacterRelationship.project_id == project_id,
        CharacterRelationship.from_character_id.in_(char_ids[:8]),
        CharacterRelationship.to_character_id.in_(char_ids[:8]),
    ).limit(10).all()

    result: list[RelationshipSnapshot] = []
    for rel in rels:
        a_id, b_id = str(rel.from_character_id), str(rel.to_character_id)
        result.append(RelationshipSnapshot(
            char_a_id=a_id, char_a_name=char_name_map.get(a_id, "?"),
            char_b_id=b_id, char_b_name=char_name_map.get(b_id, "?"),
            relation_type=rel.relation_type or "未知",
            dynamic=rel.is_dynamic or "stable",
            evolution_note=(rel.evolution_note or "")[:200],
        ))
    return result[:6]


# ── 辅助提取函数 ──────────────────────────────────────────────────

def _resolve_volume_index(node, db: Session) -> int:
    """从章纲节点解析当前卷索引（0-based）。"""
    vol_index = 0
    if node.parent_id:
        from app.models import OutlineNode
        parent = db.query(OutlineNode).filter(OutlineNode.id == node.parent_id).first()
        if parent and parent.sort_order is not None:
            vol_index = max(0, int(parent.sort_order) - 1)
    extra_vi = (node.extra or {}).get("vol_index")
    if isinstance(extra_vi, int):
        vol_index = extra_vi
    return vol_index


def _find_arc_by_vol_index(arc_list: list, vol_index: int) -> dict | None:
    """按 vol_index / sort_order 匹配卷级条目，未命中则兜底第一条。"""
    if not arc_list:
        return None
    exact = next(
        (v for v in arc_list if isinstance(v, dict) and v.get("vol_index") == vol_index), None,
    )
    if exact:
        return exact
    by_order = next(
        (v for v in arc_list if isinstance(v, dict) and v.get("sort_order") == vol_index), None,
    )
    if by_order:
        return by_order
    if vol_index < len(arc_list) and isinstance(arc_list[vol_index], dict):
        return arc_list[vol_index]
    return arc_list[0] if isinstance(arc_list[0], dict) else None


def _extract_villain_offscreen(project, node, db: Session) -> str:
    """从 Project.extra.villain_arc 提取当前卷的反派幕后动态。"""
    extra = project.extra or {}
    villain_arc = extra.get("villain_arc")
    if not villain_arc:
        return ""

    vol_index = _resolve_volume_index(node, db)

    if isinstance(villain_arc, list):
        vol_arc = _find_arc_by_vol_index(villain_arc, vol_index)
        if not vol_arc:
            return ""
        return (
            vol_arc.get("hidden_move") or vol_arc.get("vol_goal")
            or vol_arc.get("action") or vol_arc.get("description")
            or str(vol_arc)[:200]
        )

    if isinstance(villain_arc, dict):
        arcs = villain_arc.get("volumes") or villain_arc.get("arcs") or []
        if isinstance(arcs, list) and vol_index < len(arcs):
            vol_arc = arcs[vol_index]
            if isinstance(vol_arc, dict):
                return vol_arc.get("action", "") or vol_arc.get("description", "") or str(vol_arc)[:200]
            return str(vol_arc)[:200]
        return (villain_arc.get("description") or villain_arc.get("summary") or "")[:200]

    return ""


def _extract_emotional_quota(project, node) -> dict:
    """从 Project.extra.emotion_arc 提取当前卷/阶段的情绪预算。"""
    extra = project.extra or {}
    emotion_arc = extra.get("emotion_arc")
    if not emotion_arc:
        return {}

    vol_idx = max(0, (node.sort_order or 1) // 10)

    if isinstance(emotion_arc, list):
        if vol_idx < len(emotion_arc) and isinstance(emotion_arc[vol_idx], dict):
            vol = emotion_arc[vol_idx]
            return {
                "volume_tone": vol.get("dominant_emotion") or vol.get("dominant_tone") or vol.get("tone") or "",
                "budget": vol.get("net_balance") or "",
                "forbidden_tone": vol.get("forbidden_tone") or "",
            }
        return {}

    if isinstance(emotion_arc, dict):
        volumes = emotion_arc.get("volumes") or []
        if isinstance(volumes, list) and volumes and vol_idx < len(volumes):
            return volumes[vol_idx] if isinstance(volumes[vol_idx], dict) else {}
        return {
            "volume_tone": emotion_arc.get("primary_tone", ""),
            "budget": emotion_arc.get("net_balance", ""),
            "forbidden_tone": emotion_arc.get("forbidden_tone", ""),
        }

    return {}


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
