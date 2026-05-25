"""按卷懒展开章纲专用上下文构建器。

与 context.hydrate_ctx_from_project 的差异
-----------------------------------------
hydrate_ctx_from_project 仅做「数据库 → 基础字段」映射，用于补生成设定卡等
轻量场景。此模块面向「生成第 N 卷章级大纲」，需要总编辑级别的全域上下文：

Tier 1  不变量        立项定位 / 境界体系 / 世界观 / 流派指导
Tier 2  卡司状态      人物心理档案 / 关系张力台账 / 当前弧度进展
Tier 3  故事现状      故事线进度 / 伏笔台账 / 读者承诺欠账
Tier 4  时序锚点      全卷骨架 / 前卷末状态 / 反派独立时间线
Tier 5  节奏统计      已写字数/章数 / 打脸密度统计 / 情感线出现频率
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.services.bootstrap.power_registry import format_power_context_block, merge_power_into_ctx
from app.models import (
    Character,
    CharacterRelationship,
    Faction,
    Foreshadow,
    OutlineNode,
    PowerSystem,
    Project,
    ReaderPromise,
    StoryLine,
    WorldSetting,
)

if TYPE_CHECKING:
    pass


# ── Tier 1：不变量 ────────────────────────────────────────────────────────────

def _build_positioning_block(project: Project) -> tuple[dict, str]:
    """从 Project.extra 读取立项定位，返回 (positioning_dict, prompt_block)。"""
    extra = project.extra or {}
    pos = extra.get("positioning") or {}
    if not isinstance(pos, dict):
        pos = {}

    if not pos:
        return {}, ""

    lines = []
    if pos.get("target_audience"):
        lines.append(f"  目标读者：{pos['target_audience']}")
    if pos.get("tropes"):
        lines.append(f"  核心爽点：{'、'.join(pos['tropes'])}")
    if pos.get("face_slap_pattern"):
        lines.append(f"  打脸节奏：{pos['face_slap_pattern']}（硬性节奏约束，不得降频）")
    if pos.get("emotional_arc"):
        arc_desc = {
            "none": "0%—无感情线",
            "low": "~10%—点缀级",
            "medium": "~25%—中等占比",
            "high": "~40%—重要副线",
        }.get(pos["emotional_arc"], pos["emotional_arc"])
        lines.append(f"  感情线占比：{arc_desc}")
    if pos.get("pace_type"):
        pace_desc = {
            "fast": "快节奏（番茄式，3-5章一爽点）",
            "medium": "中速（起点主流，5-10章一爽点）",
            "slow": "慢节奏（文笔向，10+章一爽点）",
        }.get(pos["pace_type"], pos["pace_type"])
        lines.append(f"  节奏类型：{pace_desc}")
    if pos.get("taboo_lines"):
        lines.append(f"  红线禁忌：{'；'.join(pos['taboo_lines'])}")
    if pos.get("selling_point"):
        lines.append(f"  核心卖点：{pos['selling_point']}")

    block = "\n【立项定位（全书编辑铁律，每章必须贯彻）】\n" + "\n".join(lines)
    return pos, block


def _build_power_block(db: Session, project_id: str, ctx: dict) -> str:
    """构建详细境界体系 prompt 块（多轴全保真）。"""
    from app.models import Project

    pss = (
        db.query(PowerSystem)
        .filter(PowerSystem.project_id == project_id)
        .order_by(PowerSystem.sort_order)
        .all()
    )
    if not pss:
        return ""

    project = db.query(Project).filter(Project.id == project_id).first()
    merge_power_into_ctx(ctx, pss, project=project)
    block = format_power_context_block(ctx)
    if not block or block == "（未设定境界体系）":
        return ""
    return "\n" + block + "\n"


def _build_world_settings_block(db: Session, project_id: str) -> str:
    """提取关键世界设定卡作为 prompt 约束块。"""
    settings = (
        db.query(WorldSetting)
        .filter(WorldSetting.project_id == project_id)
        .order_by(WorldSetting.created_at)
        .all()
    )
    if not settings:
        return ""
    lines: list[str] = []
    for s in settings[:6]:
        cat = (s.extra or {}).get("category", "")
        cat_str = f"[{cat}]" if cat else ""
        lines.append(f"  {cat_str}{s.title}：{(s.content or '')[:80]}")
    return "\n【世界底层设定（章纲内容不得与之矛盾）】\n" + "\n".join(lines)


# ── Tier 2：卡司状态 ──────────────────────────────────────────────────────────

def _build_cast_ctx(db: Session, project_id: str, ctx: dict) -> str:
    """构建人物卡司 ctx 字段 + 心理档案 prompt 块。"""
    chars = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.created_at)
        .all()
    )
    if not chars:
        ctx["char_names"] = []
        ctx["protagonist"] = "主角"
        ctx["char_realms"] = {}
        ctx["char_name_to_id"] = {}
        ctx["core_char_names"] = []
        ctx["char_profiles"] = {}
        ctx["plot_npc_summary"] = ""
        return ""

    ctx["char_names"] = [c.name for c in chars[:40]]
    ctx["protagonist"] = next((c.name for c in chars if c.role == "protagonist"), chars[0].name)
    ctx["char_realms"] = {c.name: (c.current_realm or "未知") for c in chars}
    ctx["char_name_to_id"] = {c.name: str(c.id) for c in chars}
    ctx["core_char_names"] = [c.name for c in chars if c.character_tier in ("core", "arc")]
    ctx["plot_npc_summary"] = "; ".join(
        f"{c.name}（{(c.extra or {}).get('vol1_function', '')}）"
        for c in chars
        if c.character_tier == "plot" and (c.extra or {}).get("vol1_function")
    )

    # 心理档案（全部核心+弧线人物，不只主角）
    profiles: dict[str, dict] = {}
    for c in chars:
        if c.character_tier not in ("core", "arc"):
            continue
        profiles[c.name] = {
            "core_wound": (c.fear or "").strip(),
            "current_desire": (c.motivation or "").strip(),
            "arc": (c.arc or "").strip(),
            "values": (c.values or "").strip(),
            "secrets": (c.secrets or "").strip(),
            "trauma": (c.trauma or "").strip(),
            "current_realm": (c.current_realm or "未知"),
            "current_status": (c.current_status or "alive"),
            "current_location": (c.current_location or ""),
            "faction": (c.faction or ""),
            "arc_stages": c.arc_stages or [],
            "speech_style": (c.speech_style or ""),
        }
    ctx["char_profiles"] = profiles

    # Prompt 块
    lines: list[str] = []
    for name, p in profiles.items():
        realm = p.get("current_realm", "未知")
        status = p.get("current_status", "alive")
        loc = p.get("current_location", "")
        faction = p.get("faction", "")
        loc_str = f"，位置：{loc}" if loc else ""
        faction_str = f"，所属：{faction}" if faction else ""
        header = f"  【{name}｜{realm}{loc_str}{faction_str}｜{status}】"
        lines.append(header)
        if p.get("arc"):
            lines.append(f"    人物弧线：{p['arc']}")
        if p.get("core_wound"):
            lines.append(f"    核心恐惧/创伤：{p['core_wound']}")
        if p.get("current_desire"):
            lines.append(f"    当前核心欲望：{p['current_desire']}")
        if p.get("values"):
            lines.append(f"    价值观：{p['values']}")
        if p.get("secrets"):
            lines.append(f"    未暴露的秘密：{p['secrets']}（暴露时机：本卷可以引爆吗？）")
        if p.get("speech_style"):
            lines.append(f"    说话风格：{p['speech_style']}")

    if not lines:
        return ""
    return "\n【核心卡司·心理档案（章节行为必须由这些档案驱动，不得凭空给角色加设定）】\n" + "\n".join(lines)


def _build_relations_block(db: Session, project_id: str) -> tuple[str, str]:
    """构建人物关系张力台账。返回 (relation_triggers_str, prompt_block)。"""
    rels = (
        db.query(CharacterRelationship)
        .filter(CharacterRelationship.project_id == project_id)
        .all()
    )
    if not rels:
        return "（无）", ""

    triggers: list[str] = []
    lines: list[str] = []

    for r in rels:
        a = r.from_character.name if r.from_character else "?"
        b = r.to_character.name if r.to_character else "?"
        rtype = r.relation_type or "?"
        note = r.evolution_note or ""

        # evolution_note 格式：[张力]xxx；[引爆事件]yyy
        tension = ""
        trigger = ""
        for seg in note.split("；"):
            if seg.startswith("[张力]"):
                tension = seg[4:]
            elif seg.startswith("[引爆事件]"):
                trigger = seg[6:]

        if trigger:
            triggers.append(f"{a}↔{b}[{trigger}]")

        line = f"  {a}↔{b}（{rtype}，强度{r.intensity}/10）"
        if tension:
            line += f"\n    未解张力：{tension}"
        if trigger:
            line += f"\n    引爆事件：{trigger}（⚡ 选择合适章节引爆，引爆后关系不可逆变化）"
        lines.append(line)

    triggers_str = "; ".join(triggers) if triggers else "（无）"
    if not lines:
        return triggers_str, ""

    block = (
        "\n【人物关系张力台账（每段关系都有炸弹，选择引爆时机是本卷章纲核心任务之一）】\n"
        + "\n".join(lines)
    )
    return triggers_str, block


# ── Tier 3：故事现状 ──────────────────────────────────────────────────────────

def _build_storylines_ctx(db: Session, project_id: str, ctx: dict) -> str:
    """构建故事线进度 ctx + prompt 块。"""
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

    block = (
        "\n【故事线进度（本卷章纲每章至少推进一条非主线，主线不得独占所有章节）】\n"
        + "\n".join(lines)
    )
    return block


def _build_foreshadow_block(db: Session, project_id: str) -> str:
    """构建未收伏笔台账 prompt 块，按优先级降序。"""
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
    for f in foreshadows[:15]:  # 最多15条，避免 prompt 过长
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
    """构建高优先级未兑现读者承诺 prompt 块。"""
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

        # 反派时间线 hint（从卷的 extra 里读，格式不限）
        vt = (v.extra or {}).get("villain_timeline", "")
        if vt:
            villain_timeline_parts.append(f"{v.title}：{vt}")

        # 定位前卷
        if (v.sort_order or 0) == current_sort - 1:
            prev_volume = v

    volumes_block = '\n【全卷骨架（生成本卷章纲时必须知道"来路"和"去路"，确保本卷在正确位置承上启下）】\n'
    volumes_block += "\n".join(vol_lines)

    # 前卷末状态
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
    """构建反派独立行动线 prompt 块。"""
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
    face_slap_count = sum(
        1 for n in all_plans if (n.extra or {}).get("has_face_slap", False)
    )
    emotional_count = sum(
        1 for n in all_plans if (n.extra or {}).get("has_emotional_beat", False)
    )

    # 本卷前的章节数（确定全书位置）
    prev_vol_plans = [
        n for n in all_plans
        if n.parent_id != current_volume_node.id
    ]
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


# ── 主入口 ────────────────────────────────────────────────────────────────────

def build_vol_expand_ctx(
    db: Session,
    project: Project,
    volume_node: OutlineNode,
) -> tuple[dict, str]:
    """为按卷懒展开构建总编辑级上下文。

    Args:
        db:          数据库会话。
        project:     当前项目。
        volume_node: 目标卷 OutlineNode（node_type 必须为 "volume"）。

    Returns:
        (ctx_dict, editorial_prompt_block)
        - ctx_dict：传给 gen_vol_chapter_plans 的 ctx，含所有 bootstrap 级字段。
        - editorial_prompt_block：直接插入 prompt 的富上下文字符串。
    """
    project_id = str(project.id)
    ctx: dict = {
        "logline": project.logline or "",
        "premise": project.premise or "",
        "target_words": int(project.target_words or 1_200_000),
        "project_title": project.title or "未命名",
        "genre": project.genre or "玄幻",
        "world_overview": project.world_overview or "",
        "story_core": project.story_core if isinstance(project.story_core, dict) else {},
    }

    # ── 流派工具包 ────────────────────────────────────────────────────────────
    try:
        from app.services.genre_kit import get_genre_kit, normalize_genre, render_kit_for_prompt
        kit = get_genre_kit(normalize_genre(ctx["genre"]))
        ctx["genre_kit"] = kit
        ctx["genre_kit_prompt"] = render_kit_for_prompt(kit)
    except Exception:
        ctx["genre_kit"] = {}
        ctx["genre_kit_prompt"] = ""

    # ── Tier 1 块 ──────────────────────────────────────────────────────────────
    positioning, positioning_block = _build_positioning_block(project)
    ctx["positioning"] = positioning

    # 从 opening_contract 读取初始承诺
    opening_contract = (project.extra or {}).get("opening_contract", {})
    ctx["opening_contract"] = opening_contract
    ctx["settings_summary"] = ""  # 不用 world_settings 做 settings_summary，后面有独立块

    power_block = _build_power_block(db, project_id, ctx)
    world_block = _build_world_settings_block(db, project_id)

    # ── Tier 2 块 ──────────────────────────────────────────────────────────────
    cast_block = _build_cast_ctx(db, project_id, ctx)
    relation_triggers_str, relations_block = _build_relations_block(db, project_id)
    ctx["relation_triggers"] = relation_triggers_str

    # ── Tier 3 块 ──────────────────────────────────────────────────────────────
    storylines_block = _build_storylines_ctx(db, project_id, ctx)
    foreshadow_block = _build_foreshadow_block(db, project_id)
    promises_block = _build_reader_promises_block(db, project_id)

    # ── Tier 4 块 ──────────────────────────────────────────────────────────────
    villain_timelines_str, volumes_block, prev_vol_ending_block = _build_volumes_skeleton(
        db, project_id, volume_node
    )
    ctx["villain_timelines"] = [villain_timelines_str] if villain_timelines_str else []
    villain_block = _build_villain_block(db, project_id, ctx)

    # ── Tier 5 块 ──────────────────────────────────────────────────────────────
    pacing_block = _build_pacing_stats(db, project_id, volume_node)

    # ── 新步骤产物块（Step 9.5/9.8/11.5）─────────────────────────────────────
    from app.services.bootstrap.context_new_steps import build_new_steps_blocks
    emotion_arc_block, villain_arc_block, core_mysteries_block = build_new_steps_blocks(
        project, volume_node, ctx
    )

    # ── 组合 editorial_prompt_block ───────────────────────────────────────────
    editorial_blocks = [
        b for b in [
            positioning_block,
            power_block,
            world_block,
            volumes_block,
            prev_vol_ending_block,
            emotion_arc_block,
            villain_arc_block,
            core_mysteries_block,
            cast_block,
            relations_block,
            villain_block,
            storylines_block,
            foreshadow_block,
            promises_block,
            pacing_block,
        ]
        if b
    ]
    editorial_prompt_block = "\n".join(editorial_blocks)

    return ctx, editorial_prompt_block
