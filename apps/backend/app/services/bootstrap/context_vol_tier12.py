"""卷懒展开上下文构建器 — Tier 1（不变量）+ Tier 2（卡司状态）。

Tier 1：立项定位 / 境界体系 / 世界观底层设定
Tier 2：人物心理档案 / 关系张力台账
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import (
    Character,
    CharacterRelationship,
    PowerSystem,
    Project,
    WorldSetting,
)


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
    from app.services.bootstrap.power_registry import format_power_context_block, merge_power_into_ctx

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
    """提取关键世界设定卡作为 prompt 约束块（最多 6 条，仅纯叙事设定）。"""
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
    """构建人物卡司 ctx 字段 + 心理档案 prompt 块。

    Side effects on ctx: char_names, protagonist, char_realms, char_name_to_id,
    core_char_names, char_profiles, plot_npc_summary
    """
    chars = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.created_at)
        .all()
    )
    if not chars:
        ctx.update({
            "char_names": [], "protagonist": "主角", "char_realms": {},
            "char_name_to_id": {}, "core_char_names": [], "char_profiles": {},
            "plot_npc_summary": "",
        })
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
    """构建人物关系张力台账。

    Returns:
        (relation_triggers_str, prompt_block)
    """
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
