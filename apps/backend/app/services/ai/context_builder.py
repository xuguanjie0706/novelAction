"""
context_builder.py — 章节写作上下文构建服务

职责：为 AI 生成（章节起草、质检、连贯性检查、Chat 问答）
构建结构化上下文字符串（世界设定、人物档案、连续性摘要、情节档案等）。

原路径：`app/routers/ai/context.py`（已退役，仅保留兼容 re-export）。
新路径：`app/services/ai/context_builder.py`

调用方：routers/ai/ 各路由模块通过
  `from app.services.ai.context_builder import build_xxx_context`
或沿用旧路径（兼容 re-export）。
"""
import json
from typing import List, Optional
from uuid import UUID

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import (
    Chapter,
    ChapterIndex,
    Character,
    Foreshadow,
    Item,
    MemoryChunk,
    OutlineNode,
    PowerSystem,
    Project,
    Skill,
    StoryLine,
    WorldSetting,
    Faction,
)
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block
from app.utils.chapter_numbering import display_chapter_number
from app.routers.ai.constants import _SETTING_CORE_LABELS, _SETTING_FOCUS_LABELS
from app.routers.ai.text_utils import (
    brief_text,
    format_brief_line,
    plain_text,
    truncate,
)


def read_setting_section(extra: dict, key: str) -> dict:
    section = extra.get(key)
    return section if isinstance(section, dict) else {}


def format_world_setting_context(setting: WorldSetting, content_limit: int = 1200) -> str:
    extra = setting.extra if isinstance(setting.extra, dict) else {}
    category = extra.get("category") or (setting.category.name if setting.category else "setting")
    importance = extra.get("importance")
    stage = extra.get("stage")
    markers = [str(category)]
    if importance:
        markers.append(str(importance))
    if stage:
        markers.append(str(stage))

    lines = [f"[{'/'.join(markers)}] {setting.title}"]
    core = read_setting_section(extra, "core")
    focus = read_setting_section(extra, "focus")
    for key, label in _SETTING_CORE_LABELS:
        value = core.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"{label}：{value.strip()}")
    for key, label in _SETTING_FOCUS_LABELS:
        value = focus.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"{label}：{value.strip()}")

    links = extra.get("links")
    if isinstance(links, dict):
        link_parts = []
        for key, label in [
            ("faction_names", "关联势力"),
            ("character_names", "关联人物"),
            ("storyline_names", "关联故事线"),
            ("power_system_names", "关联力量体系"),
        ]:
            values = links.get(key)
            if isinstance(values, list):
                names = "、".join(str(v) for v in values if v)
                if names:
                    link_parts.append(f"{label}={names}")
        if link_parts:
            lines.append("关联：" + "；".join(link_parts))

    content = truncate(setting.content, content_limit)
    if content:
        lines.append(f"详细设定：{content}")
    return "\n".join(lines)


def build_continuity_context(
    db: Session,
    project_id: str,
    chapter: Chapter,
    outline_node: Optional[OutlineNode],
) -> str:
    """生成前的跨章事实账本：状态、伏笔、承接点、禁止事项。"""
    prev_chapter = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.sort_order < chapter.sort_order,
    ).order_by(Chapter.sort_order.desc()).first()
    current_chapter_number = display_chapter_number(chapter.title, chapter.sort_order)
    previous_chapter_number = (
        display_chapter_number(prev_chapter.title, prev_chapter.sort_order)
        if prev_chapter
        else 0
    )

    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).order_by(Character.role, Character.name).all()
    char_lines = []
    for c in characters[:10]:
        parts = [f"{c.name}"]
        if c.role:
            parts.append(f"身份={c.role}")
        if c.current_realm:
            parts.append(f"当前境界={c.current_realm}")
        if c.realm_rank is not None:
            parts.append(f"境界序号={c.realm_rank}")
        if c.current_location:
            parts.append(f"当前位置={c.current_location}")
        if c.current_status and c.current_status != "alive":
            parts.append(f"状态={c.current_status}")
        char_lines.append("、".join(parts))

    power_systems = db.query(PowerSystem).filter(
        PowerSystem.project_id == project_id
    ).order_by(PowerSystem.sort_order).all()
    power_lines = []
    for ps in power_systems[:3]:
        level_names = []
        for level in (ps.levels or [])[:8]:
            if isinstance(level, dict) and level.get("name"):
                rank = level.get("rank")
                level_names.append(f"{rank}.{level.get('name')}" if rank else level.get("name"))
        rule = truncate(ps.special_rules or ps.breakthrough_condition or ps.description, 80)
        line = f"{ps.name}"
        if level_names:
            line += f"等级顺序={' > '.join(level_names)}"
        if ps.protagonist_current_rank:
            line += f"；主角当前rank={ps.protagonist_current_rank}"
        if rule:
            line += f"；规则={rule}"
        power_lines.append(line)

    recent_chapters = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.sort_order < chapter.sort_order,
    ).order_by(Chapter.sort_order.desc()).limit(3).all()
    recent_lines = []
    for c in reversed(recent_chapters):
        source = getattr(c, "summary", None) or plain_text(c.content)[-180:]
        if source:
            recent_lines.append(
                f"第{display_chapter_number(c.title, c.sort_order)}章《{c.title}》：{truncate(source, 160)}"
            )

    mem_rows_ctx = (
        db.query(MemoryChunk, Chapter)
        .outerjoin(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(
            MemoryChunk.project_id == project_id,
            MemoryChunk.memory_type.in_(["foreshadow", "event", "character_state"]),
        )
        .order_by(func.coalesce(Chapter.sort_order, MemoryChunk.chapter_number, -1).desc())
        .limit(8)
        .all()
    )
    memory_lines = []
    for m, ch in mem_rows_ctx:
        if not (m.content or "").strip():
            continue
        num = display_chapter_number(ch.title, ch.sort_order) if ch is not None else (m.chapter_number or "?")
        memory_lines.append(f"第{num}章 {m.title or m.memory_type}：{truncate(m.content, 100)}")

    storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["planned", "active", "climax"]),
    ).order_by(StoryLine.sort_order).limit(5).all()
    storyline_lines = []
    for s in storylines:
        beats = list(s.key_beats or [])
        last_beat = ""
        if beats:
            beat = beats[-1]
            if isinstance(beat, dict):
                last_beat = beat.get("beat") or beat.get("milestone") or ""
            else:
                last_beat = str(beat)
        desc = truncate(last_beat or s.core_conflict or s.description, 90)
        storyline_lines.append(f"{s.name}（{s.status}）：{desc}")

    bridge_lines = []
    if previous_chapter_number > 0:
        bridge_lines.append(
            f"本章必须承接第{previous_chapter_number}章结尾，不得跳过报信、反应、转场等因果链。"
        )
    if outline_node and outline_node.power_milestone:
        bridge_lines.append(f"本章实力目标：{outline_node.power_milestone}")
    if outline_node and (outline_node.foreshadows_resolved or outline_node.foreshadows_laid):
        bridge_lines.append("伏笔必须有前因后果；不得凭空写角色已经知道未在前文出现的信息。")

    # ── 全局伏笔管理表：逾期优先 → priority 降序 → 时间升序 ──────────────
    # 排序逻辑：逾期伏笔（planned_resolve_chapter <= 当前章）排在最前面，
    # 确保编辑最关注的"快截止/已过期"伏笔无论 priority 高低都能进入注入窗口，
    # 不依赖 pre_write_warning 是否开启。
    _ch_num = chapter.sort_order or 0
    global_foreshadows = (
        db.query(Foreshadow)
        .filter(
            Foreshadow.project_id == project_id,
            Foreshadow.status == "open",
        )
        .order_by(
            # 0 = 逾期（planned_resolve_chapter 存在且 <= 当前章），1 = 未逾期
            case(
                (
                    (Foreshadow.planned_resolve_chapter.isnot(None))
                    & (Foreshadow.planned_resolve_chapter <= _ch_num),
                    0,
                ),
                else_=1,
            ),
            Foreshadow.priority.desc(),
            Foreshadow.created_at,
        )
        .limit(12)
        .all()
    )
    foreshadow_lines = []
    for f in global_foreshadows:
        # 逾期标记：当章号 > 0 且已超过计划回收章
        is_overdue = bool(
            _ch_num > 0
            and f.planned_resolve_chapter
            and f.planned_resolve_chapter <= _ch_num
        )
        overdue_tag = "⚠️已逾期！" if is_overdue else ""
        parts = [overdue_tag + (f.code or "F-?"), f.title]
        if f.laid_chapter_number:
            parts.append(f"(第{f.laid_chapter_number}章埋)")
        if f.planned_resolve_chapter:
            planned_label = "铺垫" if getattr(f, "planned_action", "resolve") == "develop" else "回收"
            parts.append(f"→预计第{f.planned_resolve_chapter}章{planned_label}")
        if f.description:
            parts.append(f"：{truncate(f.description, 60)}")
        foreshadow_lines.append("、".join(parts[:3]) + ("".join(parts[3:]) if len(parts) > 3 else ""))

    ban_lines = [
        "人物境界、位置、状态不得倒退或跳变，除非本章明确写出代价、原因和过渡。",
        "不得让角色掌握前文未获得的情报；新情报必须通过看见、听见、推理或前文伏笔获得。",
        "不得无提示跳过上一章钩子的直接反应。"
    ]

    sections = [
        f"截至第{previous_chapter_number}章事实表（用于生成第{current_chapter_number}章）：",
        "人物状态：" + ("；".join(char_lines) if char_lines else "无"),
        "力量体系：" + ("；".join(power_lines) if power_lines else "无"),
        "最近章节：" + ("；".join(recent_lines) if recent_lines else "无"),
        "记忆/伏笔：" + ("；".join(memory_lines) if memory_lines else "无"),
        "故事线进度：" + ("；".join(storyline_lines) if storyline_lines else "无"),
        "未解决承接点：" + ("；".join(bridge_lines) if bridge_lines else "无"),
        "禁止事项：" + "；".join(ban_lines),
    ]
    if foreshadow_lines:
        sections.insert(5, "⚠️未回收伏笔（必须可回收或持续铺垫，不得矛盾违背）：\n" +
                         "\n".join(f"  · {l}" for l in foreshadow_lines))
    return "\n".join(sections)


def fmt_index_item(item) -> str:
    if isinstance(item, dict):
        return (
            item.get("description")
            or item.get("event")
            or item.get("name")
            or item.get("note")
            or json.dumps(item, ensure_ascii=False)
        )
    return str(item)


def string_ids(values) -> set[str]:
    return {str(value) for value in (values or []) if value}


def json_ref_ids(values, key: str) -> set[str]:
    ids = set()
    for value in values or []:
        if isinstance(value, dict) and value.get(key):
            ids.add(str(value.get(key)))
    return ids


def build_writing_brief_context(
    db: Session,
    project_id: str,
    chapter: Chapter,
    outline_node: Optional[OutlineNode],
    large_context: bool = False,
) -> str:
    """Activate only the assets this chapter may consume: factions, items, and skills."""
    current_chapter_number = display_chapter_number(chapter.title, chapter.sort_order)
    involved_ids = string_ids(outline_node.involved_character_ids if outline_node else [])
    key_item_ids = string_ids(outline_node.key_item_ids if outline_node else [])
    key_skill_ids = string_ids(outline_node.key_skill_ids if outline_node else [])

    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).order_by(Character.role, Character.name).all()
    if involved_ids:
        active_characters = [c for c in characters if str(c.id) in involved_ids]
    else:
        active_characters = [
            c for c in characters
            if c.role in {"protagonist", "antagonist"}
        ][:6] or characters[:6]
    active_character_ids = {str(c.id) for c in active_characters}
    owned_item_ids = set().union(*[
        json_ref_ids(c.owned_items, "item_id") for c in active_characters
    ]) if active_characters else set()
    known_skill_ids = set().union(*[
        json_ref_ids(c.known_skills, "skill_id") for c in active_characters
    ]) if active_characters else set()
    faction_ids = {str(c.faction_id) for c in active_characters if c.faction_id}
    faction_names = {c.faction for c in active_characters if c.faction}

    items = db.query(Item).filter(
        Item.project_id == project_id
    ).order_by(Item.sort_order, Item.created_at).all()
    activated_items = []
    for item in items:
        item_id = str(item.id)
        owner_id = str(item.current_owner_id) if item.current_owner_id else ""
        first_seen = item.first_appearance_chapter or 0
        is_core_by_rarity = item.rarity in {"unique", "mythic", "legendary"} and (
            owner_id in active_character_ids
            or (first_seen and first_seen <= current_chapter_number)
        )
        if (
            item_id in key_item_ids
            or item_id in owned_item_ids
            or owner_id in active_character_ids
            or is_core_by_rarity
        ):
            activated_items.append(item)

    skills = db.query(Skill).filter(
        Skill.project_id == project_id
    ).order_by(Skill.sort_order, Skill.created_at).all()
    activated_skills = []
    for skill in skills:
        skill_id = str(skill.id)
        mastered_by = string_ids(skill.mastered_by_character_ids)
        first_seen = skill.first_appearance_chapter or 0
        if (
            skill_id in key_skill_ids
            or skill_id in known_skill_ids
            or bool(mastered_by & active_character_ids)
            or (first_seen and first_seen <= current_chapter_number and skill.grade in {"divine", "supreme"})
        ):
            activated_skills.append(skill)

    factions = db.query(Faction).filter(
        Faction.project_id == project_id
    ).order_by(Faction.sort_order, Faction.created_at).all()
    activated_factions = [
        f for f in factions
        if str(f.id) in faction_ids or f.name in faction_names
    ]

    item_limit = 12 if large_context else 5
    skill_limit = 12 if large_context else 5
    faction_limit = 10 if large_context else 4
    sections = ["【本章写前 Brief / 激活资产】"]

    if activated_factions:
        faction_lines = []
        for faction in activated_factions[:faction_limit]:
            faction_lines.append(format_brief_line(
                faction.name,
                [
                    f"立场={faction.alignment}" if faction.alignment else "",
                    f"对主角态度={faction.attitude_to_protagonist}" if faction.attitude_to_protagonist else "",
                    f"资源={brief_text(faction.resources)}" if faction.resources else "",
                    f"目标={brief_text(faction.goals)}" if faction.goals else "",
                ],
            ))
        sections.append("激活势力：" + "；".join(faction_lines))
        sections.append("势力消费方式：只把势力当作身份、资源、阻力或冲突来源；本章后若关系变化，章后复盘更新态度或故事线。")

    if activated_items:
        item_lines = []
        for item in activated_items[:item_limit]:
            item_lines.append(format_brief_line(
                item.name,
                [
                    "/".join(part for part in [item.item_type, item.rarity] if part),
                    f"状态={item.status}" if item.status else "",
                    f"效果={brief_text(item.effects)}" if item.effects else "",
                    f"限制={brief_text(item.limitations)}" if item.limitations else "",
                    f"意义={brief_text(item.story_significance)}" if item.story_significance else "",
                ],
            ))
        sections.append("激活道具/法宝：" + "；".join(item_lines))
        sections.append("道具消费方式：只使用已激活道具的已知能力；不得临场赋予新能力。若新增B级道具影响后文，章后入库并记录持有者、状态和限制。")

    if activated_skills:
        skill_lines = []
        for skill in activated_skills[:skill_limit]:
            skill_lines.append(format_brief_line(
                skill.name,
                [
                    "/".join(part for part in [skill.skill_type, skill.grade] if part),
                    f"要求={brief_text(skill.level_required)}" if skill.level_required else "",
                    f"效果={brief_text(skill.effects)}" if skill.effects else "",
                    f"限制={brief_text(skill.limitations)}" if skill.limitations else "",
                ],
            ))
        sections.append("激活功法/技能：" + "；".join(skill_lines))
        sections.append("技能消费方式：必须符合掌握者、境界、熟练度和代价；升级必须在正文写出原因，并在章后复盘更新人物技能。")

    if len(sections) == 1:
        return ""

    sections.append("C级临时资产：允许出现无名、一次性的丹药/符箓/小势力/普通招式；不得解决主冲突；若影响后续，章后复盘升格入库。")
    return "\n".join(sections)


def build_chapter_index_context(db: Session, project_id: str, chapter: Chapter) -> str:
    """最近章节索引 + 未回收伏笔，作为连续生成的主干导航。"""
    recent_rows = (
        db.query(ChapterIndex, Chapter)
        .join(Chapter, Chapter.id == ChapterIndex.chapter_id)
        .filter(
            ChapterIndex.project_id == project_id,
            Chapter.project_id == project_id,
            Chapter.sort_order < chapter.sort_order,
        )
        .order_by(Chapter.sort_order.desc())
        .limit(5)
        .all()
    )

    recent_lines = []
    for idx, ch in reversed(recent_rows):
        events = "；".join(fmt_index_item(e) for e in (idx.core_events or [])[:3])
        hook = idx.ending_hook or ""
        notes = "；".join(fmt_index_item(n) for n in (idx.continuity_notes or [])[:3])
        num = display_chapter_number(ch.title, ch.sort_order)
        parts = [f"第{num}章"]
        if idx.story_day:
            parts.append(f"故事日={idx.story_day}")
        if events:
            parts.append(f"核心事件={events}")
        if hook:
            parts.append(f"章末钩子={hook}")
        if notes:
            parts.append(f"连续性风险={notes}")
        recent_lines.append("；".join(parts))

    all_rows = (
        db.query(ChapterIndex, Chapter)
        .join(Chapter, Chapter.id == ChapterIndex.chapter_id)
        .filter(
            ChapterIndex.project_id == project_id,
            Chapter.project_id == project_id,
            Chapter.sort_order < chapter.sort_order,
        )
        .order_by(Chapter.sort_order)
        .all()
    )
    resolved_descriptions = {
        fmt_index_item(item)
        for idx, _ch in all_rows
        for item in (idx.actual_foreshadows_resolved or [])
        if fmt_index_item(item)
    }
    open_foreshadows = []
    for idx, ch in all_rows:
        num = display_chapter_number(ch.title, ch.sort_order)
        for item in (idx.actual_foreshadows_laid or []):
            desc = fmt_index_item(item)
            status = item.get("status") if isinstance(item, dict) else ""
            if not desc or desc in resolved_descriptions or status == "resolved":
                continue
            open_foreshadows.append(f"第{num}章：{desc}")

    sections = []
    if recent_lines:
        sections.append("最近章节索引：\n" + "\n".join(recent_lines))
    if open_foreshadows:
        sections.append("全量未回收伏笔：\n" + "\n".join(open_foreshadows[-12:]))
    return "\n\n".join(sections)


def build_plot_dossier_context(db: Session, project_id: str, chapter: Chapter, large_context: bool = False) -> str:
    """情节档案：章节索引主线 + 伏笔状态 + 当前活跃故事线。"""
    index_rows = (
        db.query(ChapterIndex, Chapter)
        .join(Chapter, Chapter.id == ChapterIndex.chapter_id)
        .filter(
            ChapterIndex.project_id == project_id,
            Chapter.project_id == project_id,
            Chapter.sort_order < chapter.sort_order,
        )
        .order_by(Chapter.sort_order)
        .all()
    )
    chapter_limit = 60 if large_context else 16
    index_lines = []
    for idx, ch in index_rows[-chapter_limit:]:
        num = display_chapter_number(ch.title, ch.sort_order)
        events = "；".join(fmt_index_item(e) for e in (idx.core_events or [])[: (6 if large_context else 3)])
        hook = truncate(idx.ending_hook, 220 if large_context else 120) if idx.ending_hook else ""
        notes = "；".join(fmt_index_item(n) for n in (idx.continuity_notes or [])[: (5 if large_context else 2)])
        parts = [f"第{num}章《{ch.title}》"]
        if idx.story_day:
            parts.append(f"故事日={idx.story_day}")
        if events:
            parts.append(f"核心事件={events}")
        if hook:
            parts.append(f"章末钩子={hook}")
        if notes:
            parts.append(f"连续性备注={notes}")
        index_lines.append("；".join(parts))

    foreshadow_rows = (
        db.query(Foreshadow)
        .filter(Foreshadow.project_id == project_id)
        .order_by(Foreshadow.priority.desc(), Foreshadow.created_at.asc())
        .all()
    )
    foreshadow_limit = 30 if large_context else 12
    foreshadow_lines = []
    for f in foreshadow_rows[:foreshadow_limit]:
        parts = [f.code or "F-?", f.title, f"状态={f.status}"]
        if f.laid_chapter_number:
            parts.append(f"埋点=第{f.laid_chapter_number}章")
        if f.resolved_chapter_number:
            parts.append(f"回收=第{f.resolved_chapter_number}章")
        if f.description:
            parts.append(f"说明={truncate(f.description, 200 if large_context else 90)}")
        foreshadow_lines.append("；".join(parts))

    storyline_rows = (
        db.query(StoryLine)
        .filter(
            StoryLine.project_id == project_id,
            StoryLine.status.in_(["planned", "active", "climax"]),
        )
        .order_by(StoryLine.sort_order)
        .all()
    )
    storyline_limit = 24 if large_context else 8
    storyline_lines = []
    for s in storyline_rows[:storyline_limit]:
        beats = list(s.key_beats or [])
        tail = ""
        if beats:
            last = beats[-1]
            if isinstance(last, dict):
                tail = str(last.get("beat") or last.get("milestone") or "")
            else:
                tail = str(last)
        storyline_lines.append(
            f"{s.name}（{s.line_type}/{s.status}）："
            f"{truncate(tail or s.core_conflict or s.description, 260 if large_context else 120)}"
        )

    sections = []
    if index_lines:
        sections.append("章节索引（情节档案）：\n" + "\n".join(f"- {line}" for line in index_lines))
    if foreshadow_lines:
        sections.append("伏笔档案（含已回收/未回收）：\n" + "\n".join(f"- {line}" for line in foreshadow_lines))
    if storyline_lines:
        sections.append("故事线档案（活跃中）：\n" + "\n".join(f"- {line}" for line in storyline_lines))
    return "\n\n".join(sections)


def format_outline_chat_foreshadows(node: OutlineNode) -> str:
    parts: list[str] = []
    for label, value in [
        ("埋伏笔", node.foreshadows_laid),
        ("收伏笔", node.foreshadows_resolved),
    ]:
        if not value:
            continue
        descs = [
            item.get("description", "") if isinstance(item, dict) else str(item)
            for item in value[:5]
        ]
        text = "；".join(d for d in descs if d)
        if text:
            parts.append(f"{label}={text}")
    legacy = (node.extra or {}).get("foreshadow", "") if isinstance(node.extra, dict) else ""
    if legacy and not parts:
        parts.append(f"伏笔={legacy}")
    return "；".join(parts)


def format_outline_chat_node(node: OutlineNode) -> str:
    node_type = {"volume": "卷", "arc": "篇", "chapter_plan": "章"}.get(node.node_type, node.node_type)
    parts = [f"- [{node_type}] {node.title}"]
    if node.summary:
        parts.append(f"核心事件：{truncate(node.summary, 600)}")
    if node.hook:
        parts.append(f"开篇钩子：{truncate(node.hook, 300)}")
    if node.conflict:
        parts.append(f"人物变化/冲突：{truncate(node.conflict, 400)}")
    if node.highlight:
        parts.append(f"高光/章末：{truncate(node.highlight, 400)}")
    if node.power_milestone:
        parts.append(f"实力里程碑：{truncate(node.power_milestone, 300)}")
    if node.emotional_tone:
        parts.append(f"情感基调：{node.emotional_tone}")
    if node.pacing:
        parts.append(f"节奏：{node.pacing}")
    foreshadows = format_outline_chat_foreshadows(node)
    if foreshadows:
        parts.append(foreshadows)
    extra = node.extra if isinstance(node.extra, dict) else {}
    for key, label in [("story_day", "故事日"), ("end_hook", "章末钩子"), ("pacing", "节奏补充")]:
        value = extra.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"{label}：{truncate(value, 220)}")
    return "；".join(parts)


def format_outline_chat_context(
    *,
    project: Project,
    outline_nodes: list[OutlineNode],
    characters: list[Character],
    storylines: list[StoryLine],
    power_systems: list[PowerSystem],
) -> str:
    sections = [
        "【作品】",
        f"标题：{project.title}",
    ]
    if project.genre:
        sections.append(f"类型：{project.genre}")
    if project.logline:
        sections.append(f"一句话创意：{truncate(project.logline, 800)}")
    if project.premise:
        sections.append(f"立意/故事核：{truncate(project.premise, 1200)}")

    if characters:
        sections.append("\n【人物状态】")
        for c in characters[:80]:
            head = f"- {c.name}（{c.role}）"
            if c.current_realm:
                head += f"境界={c.current_realm}"
            parts = [head]
            if c.realm_rank is not None:
                parts.append(f"境界序号={c.realm_rank}")
            if c.current_status and c.current_status != "alive":
                parts.append(f"状态={c.current_status}")
            if c.current_location:
                parts.append(f"位置={c.current_location}")
            if c.motivation:
                parts.append(f"动机={truncate(c.motivation, 240)}")
            sections.append("；".join(parts))

    if power_systems:
        sections.append("\n【力量体系】")
        for p in power_systems[:20]:
            level_names = []
            if isinstance(p.levels, list):
                level_names = [
                    item.get("name", "") if isinstance(item, dict) else str(item)
                    for item in p.levels[:20]
                ]
            parts = [f"- {p.name}（{p.system_type}）"]
            if p.description:
                parts.append(truncate(p.description, 500))
            if p.breakthrough_condition:
                parts.append(f"突破条件={truncate(p.breakthrough_condition, 400)}")
            if level_names:
                parts.append("境界序列=" + " > ".join(n for n in level_names if n))
            sections.append("；".join(parts))

    if storylines:
        sections.append("\n【故事线】")
        for s in storylines[:40]:
            parts = [f"- {s.name}（{s.line_type}/{s.status}）"]
            if s.core_conflict or s.description:
                parts.append(truncate(s.core_conflict or s.description, 500))
            if s.key_beats:
                parts.append(f"关键节拍={json.dumps(s.key_beats, ensure_ascii=False)[:1200]}")
            sections.append("；".join(parts))

    sections.append("\n【大纲树】")
    if outline_nodes:
        for node in outline_nodes[:600]:
            sections.append(format_outline_chat_node(node))
    else:
        sections.append("（暂无大纲节点）")

    return "\n".join(sections)


def format_writing_chat_context(
    *,
    project: Project,
    chapter: Chapter,
    outline_node: Optional[OutlineNode],
    prev_chapter: Optional[Chapter],
) -> str:
    sections = [
        "【作品】",
        f"标题：{project.title}",
    ]
    if project.genre:
        sections.append(f"类型：{project.genre}")
    if project.premise:
        sections.append(f"立意/故事核：{truncate(project.premise, 1200)}")

    sections.append("\n【当前章节】")
    sections.append(f"标题：{chapter.title}")
    sections.append(f"章节序号：{display_chapter_number(chapter.title, chapter.sort_order)}")

    if outline_node:
        sections.append("\n【当前章节大纲】")
        sections.append(format_outline_chat_node(outline_node))

    if prev_chapter and prev_chapter.content:
        prev_plain = plain_text(prev_chapter.content)
        sections.append("\n【上一章结尾】")
        sections.append(prev_plain[-1800:])

    sections.append("\n【当前章节正文】")
    plain = plain_text(chapter.content)
    sections.append(plain if plain else "（当前章节暂无正文）")
    return "\n".join(sections)


def append_reference_chapters_to_writing_context(
    db: Session,
    *,
    project_id: str,
    anchor_chapter_id: UUID,
    additional_chapter_ids: Optional[List[UUID]],
    base_context: str,
) -> str:
    if not additional_chapter_ids:
        return base_context
    seen: set[UUID] = set()
    ordered: list[UUID] = []
    for raw in additional_chapter_ids:
        if raw == anchor_chapter_id:
            continue
        if raw in seen:
            continue
        seen.add(raw)
        ordered.append(raw)
        if len(ordered) >= 8:
            break
    if not ordered:
        return base_context
    rows = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id, Chapter.id.in_(ordered))
        .all()
    )
    by_id = {c.id: c for c in rows}
    blocks: list[str] = []
    for cid in ordered:
        ch = by_id.get(cid)
        if not ch:
            continue
        pl = plain_text(ch.content)
        narr, _ = split_plain_manuscript_and_index_block(pl)
        body = (narr.strip() if narr.strip() else pl)[:12000]
        num = display_chapter_number(ch.title, ch.sort_order)
        blocks.append(
            f"【参考章节《{ch.title}》（序号：{num}）】\n{body or '（该章暂无正文）'}"
        )
    if not blocks:
        return base_context
    return (
        base_context
        + "\n\n【作者指定参考的其他章节（仅作对话依据；当前章见上文）】\n"
        + "\n\n".join(blocks)
    )
