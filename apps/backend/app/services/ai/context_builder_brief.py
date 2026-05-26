"""
context_builder_brief.py — 写前简报与情节档案上下文构建

职责：
  format_world_setting_context → 设定卡格式化
  build_writing_brief_context  → 激活本章使用的势力/道具/技能资产
  build_plot_dossier_context   → 章节索引 + 伏笔档案 + 故事线档案
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    Chapter,
    Character,
    ChapterIndex,
    Faction,
    Foreshadow,
    Item,
    OutlineNode,
    Skill,
    StoryLine,
    WorldSetting,
)
from app.routers.ai.constants import _SETTING_CORE_LABELS, _SETTING_FOCUS_LABELS
from app.routers.ai.text_utils import brief_text, format_brief_line, truncate
from app.services.ai.context_builder_continuity import fmt_index_item
from app.utils.chapter_numbering import display_chapter_number


def read_setting_section(extra: dict, key: str) -> dict:
    """从设定卡 extra JSON 中读取指定节（core / focus），缺省返回空 dict。"""
    section = extra.get(key)
    return section if isinstance(section, dict) else {}


def string_ids(values) -> set[str]:
    """将 UUID/str 列表转换为字符串 ID 集合，跳过空值。"""
    return {str(value) for value in (values or []) if value}


def json_ref_ids(values, key: str) -> set[str]:
    """从 JSON 字段列表中提取指定 key 的值集合（用于 owned_items / known_skills）。"""
    ids = set()
    for value in values or []:
        if isinstance(value, dict) and value.get(key):
            ids.add(str(value.get(key)))
    return ids


def format_world_setting_context(setting: WorldSetting, content_limit: int = 1200) -> str:
    """将 WorldSetting ORM 对象格式化为单段上下文文本。"""
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


def build_writing_brief_context(
    db: Session,
    project_id: str,
    chapter: Chapter,
    outline_node: Optional[OutlineNode],
    large_context: bool = True,
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

    item_limit, skill_limit, faction_limit = 12, 12, 10
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


def build_plot_dossier_context(db: Session, project_id: str, chapter: Chapter, large_context: bool = True) -> str:
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
    chapter_limit = 60
    index_lines = []
    for idx, ch in index_rows[-chapter_limit:]:
        num = display_chapter_number(ch.title, ch.sort_order)
        events = "；".join(fmt_index_item(e) for e in (idx.core_events or [])[:6])
        hook = truncate(idx.ending_hook, 220) if idx.ending_hook else ""
        notes = "；".join(fmt_index_item(n) for n in (idx.continuity_notes or [])[:5])
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
    foreshadow_lines = []
    for f in foreshadow_rows[:30]:
        parts = [f.code or "F-?", f.title, f"状态={f.status}"]
        if f.laid_chapter_number:
            parts.append(f"埋点=第{f.laid_chapter_number}章")
        if f.resolved_chapter_number:
            parts.append(f"回收=第{f.resolved_chapter_number}章")
        if f.description:
            parts.append(f"说明={truncate(f.description, 200)}")
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
    storyline_lines = []
    for s in storyline_rows[:24]:
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
            f"{truncate(tail or s.core_conflict or s.description, 260)}"
        )

    sections = []
    if index_lines:
        sections.append("章节索引（情节档案）：\n" + "\n".join(f"- {line}" for line in index_lines))
    if foreshadow_lines:
        sections.append("伏笔档案（含已回收/未回收）：\n" + "\n".join(f"- {line}" for line in foreshadow_lines))
    if storyline_lines:
        sections.append("故事线档案（活跃中）：\n" + "\n".join(f"- {line}" for line in storyline_lines))
    return "\n\n".join(sections)
