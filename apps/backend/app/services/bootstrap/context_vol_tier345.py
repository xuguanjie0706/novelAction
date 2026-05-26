"""卷懒展开上下文构建器 — Tier 3（故事现状）+ Tier 4（时序锚点）+ Tier 5（节奏统计）。

Tier 3：故事线进度 / 伏笔台账 / 读者承诺欠账
Tier 4：全卷骨架 / 前卷末状态 / 反派独立时间线
Tier 5：已写字数/章数 / 打脸密度统计 / 情感线出现频率
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import (
    Character,
    Foreshadow,
    OutlineNode,
    Project,
    ReaderPromise,
    StoryLine,
)


# ── Tier 3：故事现状 ──────────────────────────────────────────────────────────

def _build_storylines_ctx(db: Session, project_id: str, ctx: dict) -> str:
    """构建故事线进度 ctx 字段 + prompt 块。

    Side effects on ctx: storyline_summary, storyline_ids
    """
    sls = (
        db.query(StoryLine)
        .filter(StoryLine.project_id == project_id)
        .order_by(StoryLine.sort_order)
        .all()
    )
    if not sls:
        ctx["storyline_summary"] = "（未设定）"
        ctx["storyline_ids"] = {}
        return ""

    ctx["storyline_summary"] = " | ".join(f"{sl.name}（{sl.line_type}）" for sl in sls)
    ctx["storyline_ids"] = {sl.name: str(sl.id) for sl in sls}

    lines: list[str] = []
    for sl in sls:
        status_label = {
            "planned": "待启动",
            "active": "进行中",
            "paused": "暂停",
            "resolved": "已收束",
        }.get(sl.status or "active", sl.status or "active")
        line = f"  [{sl.line_type}]{sl.name}（{status_label}）"
        if sl.description:
            line += f"：{sl.description[:60]}"
        if sl.core_conflict:
            line += f"\n    核心矛盾：{sl.core_conflict[:60]}"
        if sl.resolution_direction:
            line += f"\n    预计收束：{sl.resolution_direction[:50]}"
        lines.append(line)

    return (
        "\n【故事线进度（本卷章纲每章至少推进一条非主线，主线不得独占所有章节）】\n"
        + "\n".join(lines)
    )


def _build_foreshadow_block(db: Session, project_id: str) -> str:
    """构建未收伏笔台账 prompt 块，按优先级降序（最多 15 条）。"""
    foreshadows = (
        db.query(Foreshadow)
        .filter(
            Foreshadow.project_id == project_id,
            Foreshadow.status == "open",
        )
        .order_by(Foreshadow.priority.desc(), Foreshadow.created_at)
        .all()
    )
    if not foreshadows:
        return ""

    lines: list[str] = []
    for f in foreshadows[:15]:
        urgency = ""
        if (f.planned_resolve_chapter or 0) > 0:
            urgency = f"→预计第{f.planned_resolve_chapter}章收"
        priority_label = {5: "🔴关键", 4: "🟠重要", 3: "🟡普通", 2: "🟢次要", 1: "⚪背景"}.get(
            f.priority or 3, "🟡普通"
        )
        line = f"  {priority_label}[{f.code or 'F-?'}]{f.title}"
        if f.description:
            line += f"：{f.description[:60]}"
        if urgency:
            line += f" {urgency}"
        if f.laid_chapter_number:
            line += f"（埋于第{f.laid_chapter_number}章）"
        if f.max_distance and f.laid_chapter_number:
            line += f"（最晚第{f.laid_chapter_number + f.max_distance}章收回，否则超期）"
        lines.append(line)

    return (
        "\n【未收伏笔台账（高优先级伏笔必须在本卷安排回收章节，不得无限推迟）】\n"
        + "\n".join(lines)
        + "\n  ⚠️ 🔴关键伏笔必须在本卷指定兑现章节；🟠重要伏笔至少完成「加热」推进。"
    )


def _build_reader_promises_block(db: Session, project_id: str) -> str:
    """构建高优先级未兑现读者承诺 prompt 块（最多 10 条）。"""
    promises = (
        db.query(ReaderPromise)
        .filter(
            ReaderPromise.project_id == project_id,
            ReaderPromise.status == "open",
        )
        .order_by(ReaderPromise.priority.desc())
        .limit(10)
        .all()
    )
    if not promises:
        return ""

    lines: list[str] = []
    for p in promises:
        ptype_label = {
            "chapter_ending": "章末预告",
            "volume_ending": "卷末预告",
            "name_implication": "名字暗示",
            "chapter_comment_consensus": "评区共识",
            "protagonist_claim": "主角自述承诺",
        }.get(p.promise_type or "", p.promise_type or "?")
        priority_label = {5: "🔴", 4: "🟠", 3: "🟡", 2: "🟢", 1: "⚪"}.get(p.priority or 3, "🟡")
        line = f"  {priority_label}P{p.priority}[{ptype_label}] {p.promise_text[:100]}"
        if p.expected_chapter_window:
            line += f"（需在{p.expected_chapter_window}章内兑现）"
        lines.append(line)

    return (
        "\n【读者承诺欠债（对读者作出过的承诺，拖欠会直接导致流失）】\n"
        + "\n".join(lines)
        + "\n  ⚠️ 🔴🟠级承诺必须在本卷章纲中指定具体兑现章节，不得用「下卷」打发。"
    )


# ── Tier 4：时序锚点 ──────────────────────────────────────────────────────────

def _build_volumes_skeleton(
    db: Session, project_id: str, current_volume_node: OutlineNode
) -> tuple[str, str, str]:
    """构建全卷骨架 + 前卷末状态。

    Returns:
        (villain_timelines_str, volumes_block, prev_vol_ending_block)
    """
    volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order)
        .all()
    )

    current_sort = current_volume_node.sort_order or 0
    prev_volume: OutlineNode | None = None
    villain_timeline_parts: list[str] = []

    vol_lines: list[str] = []
    for v in volumes:
        is_current = v.id == current_volume_node.id
        marker = " ← 当前卷（生成目标）" if is_current else ""
        state = "✓已写" if (v.sort_order or 0) < current_sort else ("⟵目标" if is_current else "待写")
        line = f"  [{state}] {v.title}（phase={v.phase}，{(v.extra or {}).get('planned_chapters', 30)}章）{marker}"
        if v.summary:
            line += f"\n      卷摘要：{v.summary[:80]}"
        if v.conflict:
            line += f"\n      核心冲突：{v.conflict[:60]}"
        if v.hook:
            line += f"\n      卷末悬念种子：{v.hook[:60]}"
        vol_lines.append(line)

        vt = (v.extra or {}).get("villain_timeline", "")
        if vt:
            villain_timeline_parts.append(f"{v.title}：{vt}")

        if (v.sort_order or 0) == current_sort - 1:
            prev_volume = v

    volumes_block = '\n【全卷骨架（生成本卷章纲时必须知道"来路"和"去路"，确保本卷在正确位置承上启下）】\n'
    volumes_block += "\n".join(vol_lines)

    prev_vol_ending_block = ""
    if prev_volume:
        prev_vol_ending_block = (
            f"\n【前卷末状态（本卷第1章必须从这里自然接续，不能出现时间跳跃或逻辑断层）】\n"
            f"  前卷：{prev_volume.title}\n"
        )
        if prev_volume.summary:
            prev_vol_ending_block += f"  前卷结局：{prev_volume.summary[:100]}\n"
        if prev_volume.hook:
            prev_vol_ending_block += f"  留给本卷的悬念种子：{prev_volume.hook[:100]}\n"
        if prev_volume.conflict:
            prev_vol_ending_block += f"  前卷遗留冲突（本卷需要继承或收束）：{prev_volume.conflict[:80]}\n"

    villain_timelines_str = "；".join(villain_timeline_parts) if villain_timeline_parts else ""
    return villain_timelines_str, volumes_block, prev_vol_ending_block


def _build_villain_block(db: Session, project_id: str, ctx: dict) -> str:
    """构建反派独立行动线 prompt 块（仅 core/arc 级反派）。"""
    chars = (
        db.query(Character)
        .filter(
            Character.project_id == project_id,
            Character.role == "antagonist",
        )
        .all()
    )
    if not chars:
        return ""

    lines: list[str] = []
    for c in chars:
        if c.character_tier not in ("core", "arc"):
            continue
        line = f"  【{c.name}·反派线】境界：{c.current_realm or '未知'}，当前状态：{c.current_status or 'alive'}"
        if c.motivation:
            line += f"\n    当前目标：{c.motivation[:60]}"
        if c.arc:
            line += f"\n    反派弧线：{c.arc[:60]}"
        extra = c.extra or {}
        if extra.get("debt_to"):
            line += f"\n    欠债/仇怨：对「{extra['debt_to']}」（预计第{extra.get('detonation_vol', '?')}卷引爆）"
        lines.append(line)

    if not lines:
        return ""

    return (
        "\n【反派独立行动线（反派不是主角的被动陪衬，有自己独立的计划和行动节奏）】\n"
        + "\n".join(lines)
        + "\n  ⚠️ 每5章内反派必须至少有1次对主角造成实质影响的独立行动，即使不在主角视角。"
    )


# ── Tier 5：节奏统计 ──────────────────────────────────────────────────────────

def _build_pacing_stats(db: Session, project_id: str, current_volume_node: OutlineNode) -> str:
    """统计已写章数 / 打脸分布 / 情感章节比例，供 AI 判断当前节奏状态。"""
    all_plans = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "chapter_plan",
        )
        .all()
    )
    if not all_plans:
        return ""

    total = len(all_plans)
    face_slap_count = sum(1 for n in all_plans if (n.extra or {}).get("has_face_slap", False))
    emotional_count = sum(1 for n in all_plans if (n.extra or {}).get("has_emotional_beat", False))

    prev_vol_plans = [n for n in all_plans if n.parent_id != current_volume_node.id]
    current_vol_start_chapter = len(prev_vol_plans) + 1

    stats_lines = [
        f"  全书已规划章节：{total}章（本卷从第{current_vol_start_chapter}章开始编号）",
    ]
    if total > 0:
        stats_lines.append(
            f"  打脸章节密度：{face_slap_count}/{total}章 = {face_slap_count/total*100:.0f}%"
        )
        stats_lines.append(
            f"  情感章节密度：{emotional_count}/{total}章 = {emotional_count/total*100:.0f}%"
        )

    return (
        "\n【全书节奏统计（供本卷调整密度，不要让某类章节过于集中）】\n"
        + "\n".join(stats_lines)
    )
