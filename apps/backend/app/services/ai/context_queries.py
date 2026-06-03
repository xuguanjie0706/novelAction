"""
context_queries.py — 分层检索共享查询函数

设计动机：写正文时，Bootstrap 生成的设定应该按「本章需要什么」来检索，
而非全量注入。本模块提供按 OutlineNode 索引过滤的查询函数，
供 context_assembler.py 各粒度 assemble 方法调用。

职责边界：
- 仅做 DB 查询 + 格式化为文本块，不写库、不调用 LLM
- 每个函数返回 str（可直接拼入 prompt）
- 查询结果按相关性裁剪，控制 token 消耗
"""
from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    Character,
    CharacterRelationship,
    Faction,
    Foreshadow,
    OutlineNode,
    Project,
    ReaderPromise,
    StoryLine,
    WorldSetting,
)
from app.routers.ai.text_utils import truncate

logger = logging.getLogger(__name__)


# ── 人物：按 involved_character_ids 过滤，含 appearance/trauma ──

def query_filtered_characters(
    db: Session,
    project_id: str,
    char_ids: list[str],
) -> list[Character]:
    """
    按 ID 列表查询人物，若列表为空则回退查核心角色（protagonist/antagonist）。

    Args:
        char_ids: OutlineNode.involved_character_ids 解析后的 UUID 字符串列表
    Returns:
        Character ORM 对象列表（最多 8 个）
    """
    if char_ids:
        rows = (
            db.query(Character)
            .filter(
                Character.project_id == project_id,
                Character.id.in_([UUID(c) for c in char_ids[:8]]),
            )
            .all()
        )
        if rows:
            return rows

    # 回退：核心角色
    return (
        db.query(Character)
        .filter(
            Character.project_id == project_id,
            Character.role.in_(["protagonist", "antagonist"]),
        )
        .limit(6)
        .all()
    )


def format_character_block(char: Character) -> str:
    """
    格式化单个人物为 prompt 文本块。

    相比旧版 _build_character_summary，新增 appearance / clothing_style / trauma 字段，
    并保留 speech_kit / arc_stages 等已有字段。
    """
    parts = [f"{char.name}（{char.role}"]
    if char.alias:
        parts.append(f"别名:{char.alias}")
    if char.current_realm:
        parts.append(f"境界:{char.current_realm}")
    if char.realm_rank is not None:
        parts.append(f"境界序号:{char.realm_rank}")
    if char.current_location:
        parts.append(f"位置:{char.current_location}")
    if char.current_status and char.current_status != "alive":
        parts.append(f"状态:{char.current_status}")
    parts.append(f"）性格:{(char.personality or '')[:60]}")
    if char.speech_style:
        parts.append(f"语风:{truncate(char.speech_style, 100)}")

    # --- 以下为新增/补全字段 ---
    if char.appearance:
        parts.append(f"外貌:{truncate(char.appearance, 120)}")
    if char.clothing_style:
        parts.append(f"服饰:{truncate(char.clothing_style, 80)}")
    if char.trauma:
        parts.append(f"心理创伤:{truncate(char.trauma, 100)}")

    # --- 已有字段 ---
    if char.motivation:
        parts.append(f"动机:{truncate(char.motivation, 180)}")
    if char.values:
        parts.append(f"价值观:{truncate(char.values, 180)}")
    if char.fear:
        parts.append(f"恐惧:{truncate(char.fear, 140)}")
    if char.secrets:
        parts.append(f"秘密:{truncate(char.secrets, 180)}")

    # 技能/道具概要
    if char.known_skills:
        names = [
            sk.get("skill_name", "") if isinstance(sk, dict) else str(sk)
            for sk in char.known_skills[:6]
        ]
        parts.append(f"技能:[{'、'.join(n for n in names if n)}]")
    if char.owned_items:
        names = [
            it.get("item_name", "") if isinstance(it, dict) else str(it)
            for it in char.owned_items[:6]
        ]
        parts.append(f"持有:[{'、'.join(n for n in names if n)}]")

    # speech_kit
    _kit = char.speech_kit if isinstance(char.speech_kit, dict) else {}
    if _kit:
        _sig = [str(w) for w in (_kit.get("signature_words") or []) if w][:5]
        if _sig:
            parts.append(f"标志词:[{'、'.join(_sig)}]")
        _samples = [str(s) for s in (_kit.get("sample_dialogues") or []) if s][-3:]
        if _samples:
            parts.append("样本台词:「" + "」｜「".join(_samples) + "」")

    # arc_stages：当前阶段
    _stages = char.arc_stages if isinstance(char.arc_stages, list) else []
    _cur = next(
        (s for s in _stages if isinstance(s, dict) and not s.get("completed")),
        _stages[-1] if _stages else None,
    )
    if isinstance(_cur, dict) and _cur.get("label"):
        parts.append(f"当前弧线:{_cur['label']}")
        if _cur.get("description"):
            parts.append(f"弧线说明:{truncate(_cur['description'], 100)}")

    return "  ".join(parts)


# ── 人物关系：出场人物两两关系 ──

def query_relationships_block(
    db: Session,
    project_id: str,
    char_ids: list[str],
) -> str:
    """
    查询出场人物之间的关系，格式化为 prompt 文本块。

    仅查 from_character_id 和 to_character_id 都在 char_ids 内的关系，
    避免注入不相关角色的关系噪音。

    Args:
        char_ids: 本章出场人物 ID 字符串列表
    Returns:
        格式化的关系速查文本；无关系时返回空字符串
    """
    if len(char_ids) < 2:
        return ""

    uuid_ids = [UUID(c) for c in char_ids]
    rows = (
        db.query(CharacterRelationship)
        .filter(
            CharacterRelationship.project_id == project_id,
            CharacterRelationship.from_character_id.in_(uuid_ids),
            CharacterRelationship.to_character_id.in_(uuid_ids),
        )
        .all()
    )
    if not rows:
        return ""

    # 预查人物名
    name_map: dict[str, str] = {}
    chars = (
        db.query(Character.id, Character.name)
        .filter(Character.id.in_(uuid_ids))
        .all()
    )
    for c in chars:
        name_map[str(c.id)] = c.name

    lines = ["【人物关系速查（本章出场人物间）】"]
    for r in rows:
        from_name = name_map.get(str(r.from_character_id), "?")
        to_name = name_map.get(str(r.to_character_id), "?")
        desc = truncate(r.description, 80) if r.description else ""
        dynamic = f"（{r.is_dynamic}）" if r.is_dynamic and r.is_dynamic != "stable" else ""
        evo = f" 演变:{truncate(r.evolution_note, 60)}" if r.evolution_note else ""
        lines.append(
            f"  {from_name} →{r.relation_type or '?'}→ {to_name}"
            f" 强度{r.intensity or '?'}/10{dynamic}"
            f" {desc}{evo}"
        )

    return "\n".join(lines)


# ── 势力：按出场人物 faction_id 查询（含父级） ──

def query_related_factions_block(
    db: Session,
    project_id: str,
    characters: list[Character],
) -> str:
    """
    从出场人物的 faction_id 出发，查相关势力（含父级），格式化为文本块。

    相比旧版只注入 name/alignment/attitude，新增 territory / history / parent 信息。
    """
    faction_ids: set[UUID] = set()
    for c in characters:
        if c.faction_id:
            faction_ids.add(c.faction_id)
    if not faction_ids:
        return ""

    factions = (
        db.query(Faction)
        .filter(Faction.project_id == project_id, Faction.id.in_(list(faction_ids)))
        .all()
    )
    if not factions:
        return ""

    # 也查父级势力
    parent_ids = {f.parent_faction_id for f in factions if f.parent_faction_id} - faction_ids
    parents = []
    if parent_ids:
        parents = (
            db.query(Faction)
            .filter(Faction.id.in_(list(parent_ids)))
            .all()
        )

    all_factions = factions + parents
    lines = ["【相关势力档案】"]
    for f in all_factions:
        line = f"  {f.name}（{f.faction_type}/{f.alignment}）"
        if f.attitude_to_protagonist:
            line += f" 对主角:{f.attitude_to_protagonist}"
        if f.territory:
            line += f" 领地:{truncate(f.territory, 80)}"
        if f.goals:
            line += f" 目标:{truncate(f.goals, 100)}"
        if f.resources:
            line += f" 资源:{truncate(f.resources, 60)}"
        if f.strength_level:
            line += f" 实力:{f.strength_level}"
        is_parent = f.id in parent_ids
        if is_parent:
            line += " [上级势力]"
        lines.append(line)

    return "\n".join(lines)


# ── 故事线：按 OutlineNode.storyline_ids 过滤 ──

def query_filtered_storylines_block(
    db: Session,
    project_id: str,
    storyline_ids: list[str],
) -> str:
    """
    按 storyline_ids 过滤查询活跃故事线，格式化为文本块。

    若 storyline_ids 为空，回退查所有 active/climax 状态的故事线（最多 4 条）。

    .. deprecated::
        写作路径请优先使用 ``storyline_weave_engine.query_storyline_weave_context_block``；
        本函数仍作为无织网数据时的摘要回退。
    """
    if storyline_ids:
        uuid_ids = [UUID(s) for s in storyline_ids[:6]]
        rows = (
            db.query(StoryLine)
            .filter(StoryLine.project_id == project_id, StoryLine.id.in_(uuid_ids))
            .order_by(StoryLine.sort_order)
            .all()
        )
    else:
        rows = (
            db.query(StoryLine)
            .filter(
                StoryLine.project_id == project_id,
                StoryLine.status.in_(["active", "climax"]),
            )
            .order_by(StoryLine.sort_order)
            .limit(4)
            .all()
        )

    if not rows:
        return ""

    lines = []
    for s in rows:
        desc = truncate(s.core_conflict or s.description, 200)
        beats = json.dumps(s.key_beats or [], ensure_ascii=False)[:600]
        lines.append(
            f"- {s.name}（{s.line_type}/{s.status}）：{desc}；关键节拍={beats}"
        )

    return "\n".join(lines)


# ── 伏笔：窗口内到期（非全量） ──

def query_due_foreshadows_block(
    db: Session,
    project_id: str,
    chapter_number: int,
    window: int = 5,
) -> str:
    """
    查询到期/即将到期的伏笔，而非全量。

    窗口范围：[chapter_number - 2, chapter_number + window]
    高优先级（priority >= 4）始终注入。
    """
    all_open = (
        db.query(Foreshadow)
        .filter(
            Foreshadow.project_id == project_id,
            Foreshadow.status == "open",
        )
        .order_by(Foreshadow.priority.desc())
        .all()
    )

    relevant = []
    for f in all_open:
        target = f.planned_resolve_chapter
        # 高优先级始终注入
        if f.priority and f.priority >= 4:
            relevant.append(f)
            continue
        # 在窗口内
        if target and (chapter_number - 2) <= target <= (chapter_number + window):
            relevant.append(f)
            continue
        # 已逾期
        if target and target <= chapter_number:
            relevant.append(f)

    if not relevant:
        return ""

    lines = ["【当前伏笔台账（到期/高优先级）】"]
    for f in relevant[:10]:
        overdue = "⚠️逾期 " if (f.planned_resolve_chapter and f.planned_resolve_chapter <= chapter_number) else ""
        code = f.code or "—"
        lines.append(
            f"  {overdue}{code} {f.title or ''}"
            f" | 目标第{f.planned_resolve_chapter or '?'}章"
            f" | P{f.priority or '?'}"
            f" | {truncate(f.description, 80)}"
        )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 核心谜题：按当前卷号过滤"禁止/允许揭示"（当前完全缺失）
# ═══════════════════════════════════════════════════════════════

def query_mystery_constraints_block(
    project: Project,
    volume_index: int,
) -> str:
    """
    从 Project.extra.core_mysteries 读取跨卷核心谜题预分配。

    按当前卷号筛选出「本卷可揭示」和「本卷禁止揭示」的谜题，
    作为硬约束注入，防止 AI 过早泄底。

    Args:
        volume_index: 当前卷序号（0-based）
    """
    extra = project.extra if isinstance(project.extra, dict) else {}
    mysteries = extra.get("core_mysteries")
    if not mysteries or not isinstance(mysteries, list):
        return ""

    allowed = []
    forbidden = []

    for m in mysteries:
        if not isinstance(m, dict):
            continue
        name = m.get("name") or m.get("title") or ""
        reveal_vol = m.get("reveal_volume") or m.get("reveal_vol")
        hint_vols = m.get("hint_volumes") or []

        if reveal_vol is not None:
            # reveal_volume 是 1-based
            if reveal_vol == volume_index + 1:
                allowed.append(f"  ✅ 可揭示：{name} — {truncate(m.get('description', ''), 80)}")
            elif reveal_vol > volume_index + 1:
                forbidden.append(f"  🚫 禁止揭示：{name}（计划第{reveal_vol}卷揭示）")
        # hint_volumes 中包含当前卷
        if isinstance(hint_vols, list) and (volume_index + 1) in hint_vols:
            allowed.append(f"  💡 可暗示：{name} — 留线索但不揭底")

    if not allowed and not forbidden:
        return ""

    lines = ["【核心谜题约束（本卷）】"]
    lines.extend(allowed)
    lines.extend(forbidden)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 读者承诺：窗口内到期（复用现有逻辑但更精简）
# ═══════════════════════════════════════════════════════════════

def query_due_promises_block(
    db: Session,
    project_id: str,
    chapter_number: int,
) -> str:
    """
    查询窗口内到期的读者承诺。

    与旧版 _build_reader_promise_context 类似，但更精简：
    - 必须兑现：expected_chapter_window 已过或本章即到
    - 可以兑现：高优先级 + 3 章内到期
    """
    open_promises = (
        db.query(ReaderPromise)
        .filter(
            ReaderPromise.project_id == project_id,
            ReaderPromise.status == "open",
        )
        .order_by(ReaderPromise.priority.desc())
        .all()
    )

    if not open_promises:
        return ""

    must = []
    can = []
    for p in open_promises:
        window_end = p.expected_chapter_window or 9999
        if window_end <= chapter_number:
            must.append(p)
        elif window_end <= chapter_number + 3 or (p.priority and p.priority >= 4):
            can.append(p)

    if not must and not can:
        return ""

    lines = []
    if must:
        lines.append("【必须兑现的读者承诺（已逾期或本章到期）】")
        for p in must[:5]:
            lines.append(f"  ★{'★' * min(p.priority or 1, 5)} {p.promise_type}: {truncate(p.promise_text, 100)}")
    if can:
        lines.append("【可以兑现的读者承诺（高优先级/即将到期）】")
        for p in can[:5]:
            lines.append(f"  P{p.priority or '?'} {p.promise_type}: {truncate(p.promise_text, 100)}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 情绪弧 + 反派弧：按当前卷提取（非全量）
# ═══════════════════════════════════════════════════════════════

def query_narrative_arc_block(
    project: Project,
    volume_index: int,
) -> str:
    """
    从 Project.extra 中提取当前卷的 emotion_arc 和 villain_arc 片段。

    Args:
        volume_index: 当前卷序号（0-based）
    Returns:
        本卷的情绪/反派约束文本块
    """
    extra = project.extra if isinstance(project.extra, dict) else {}
    lines = []

    # emotion_arc
    emotion = extra.get("emotion_arc")
    if isinstance(emotion, list) and volume_index < len(emotion):
        vol_emo = emotion[volume_index]
        if isinstance(vol_emo, dict):
            tone = vol_emo.get("dominant_tone") or vol_emo.get("tone") or ""
            deposit = vol_emo.get("deposit") or ""
            withdraw = vol_emo.get("withdraw") or ""
            net = vol_emo.get("net_balance") or ""
            lines.append("【本卷情绪节律】")
            if tone:
                lines.append(f"  主色调：{tone}")
            if deposit:
                lines.append(f"  情绪存入：{truncate(str(deposit), 100)}")
            if withdraw:
                lines.append(f"  情绪消耗：{truncate(str(withdraw), 100)}")
            if net:
                lines.append(f"  净余额：{net}")

    # villain_arc
    villain = extra.get("villain_arc")
    if isinstance(villain, list) and volume_index < len(villain):
        vol_vil = villain[volume_index]
        if isinstance(vol_vil, dict):
            desire = vol_vil.get("desire") or ""
            obstacle = vol_vil.get("obstacle") or ""
            blind_spot = vol_vil.get("blind_spot") or ""
            lines.append("【本卷反派行动线】")
            if desire:
                lines.append(f"  欲望：{desire}")
            if obstacle:
                lines.append(f"  障碍：{obstacle}")
            if blind_spot:
                lines.append(f"  盲点：{blind_spot}（⚠️ 反派不可自知此盲点）")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 世界观设定：按语义相关性过滤（替代全量注入）
# ═══════════════════════════════════════════════════════════════

def query_relevant_settings_block(
    db: Session,
    project_id: str,
    query_keywords: str,
    max_count: int = 4,
) -> str:
    """
    按关键词匹配过滤世界观设定（简单文本匹配，非 embedding）。

    从章纲 summary + hook 提取关键词，只注入标题/内容包含关键词的设定。
    未匹配到任何设定时，回退注入最重要的 2 条。

    Args:
        query_keywords: 章纲 summary + hook 拼接的查询文本
        max_count: 最多注入几条设定
    """
    all_settings = (
        db.query(WorldSetting)
        .filter(WorldSetting.project_id == project_id)
        .all()
    )
    if not all_settings:
        return ""

    if not query_keywords.strip():
        # 无关键词，返回前 2 条
        selected = all_settings[:2]
    else:
        # 简单关键词匹配
        keywords = set(query_keywords.replace("、", " ").replace("，", " ").split())
        keywords = {k for k in keywords if len(k) >= 2}  # 过滤太短的词

        scored: list[tuple[int, WorldSetting]] = []
        for s in all_settings:
            text = f"{s.title or ''} {s.content or ''}"
            score = sum(1 for k in keywords if k in text)
            if score > 0:
                scored.append((score, s))

        scored.sort(key=lambda x: -x[0])
        selected = [s for _, s in scored[:max_count]]

        # 无匹配，回退
        if not selected:
            selected = all_settings[:2]

    lines = []
    for s in selected:
        content = truncate(s.content, 400) if s.content else ""
        category = ""
        if hasattr(s, "extra") and isinstance(s.extra, dict):
            category = s.extra.get("category", "")
        if category:
            category = f"[{category}] "
        lines.append(f"- {category}{s.title or '未命名'}：{content}")

    return "\n".join(lines)
