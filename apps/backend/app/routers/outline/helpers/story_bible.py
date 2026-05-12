"""大纲质检用的结构化事实账本（约束清单）。"""
from __future__ import annotations

from app.models import (
    Character,
    Faction,
    Foreshadow,
    Item,
    PowerSystem,
    Project,
    Skill,
    StoryLine,
    WorldSetting,
)

from app.routers.outline.helpers.chapter_context import _format_json_list
from app.routers.outline.helpers.text_utils import _clean_outline_text

def _format_outline_quality_story_bible(
    *,
    project: Project,
    settings: list[WorldSetting],
    characters: list[Character],
    storylines: list[StoryLine],
    power_systems: list[PowerSystem],
    factions: list[Faction],
    items: list[Item],
    foreshadows: list[Foreshadow],
    skills: list[Skill] | None = None,
) -> str:
    """
    Build a compact fact ledger for outline QA.
    It is intentionally structured as constraints, not prose, so the model can
    catch deaths, item symbolism, world rules, and arc regressions.
    """
    sections: list[str] = []
    story_core = project.story_core if isinstance(project.story_core, dict) else {}

    core_lines = []
    if project.premise:
        core_lines.append(f"立意/边界：{_clean_outline_text(project.premise, 240)}")
    if project.world_overview:
        core_lines.append(f"世界概览：{_clean_outline_text(project.world_overview, 220)}")
    if story_core.get("theme"):
        core_lines.append(f"主题命题：{_clean_outline_text(story_core.get('theme'), 180)}")
    if core_lines:
        sections.append("【作品核心约束】\n" + "\n".join(f"- {line}" for line in core_lines))

    if settings:
        lines = []
        for setting in settings[:12]:
            tags = _format_json_list(setting.tags, max_items=4)
            tag_text = f" [{tags}]" if tags else ""
            lines.append(
                f"- {setting.title}{tag_text}：{_clean_outline_text(setting.content, 220)}"
            )
        sections.append("【世界观/规则卡】\n" + "\n".join(lines))

    if characters:
        lines = []
        for character in characters[:16]:
            stages = _format_json_list(character.arc_stages, max_items=4)
            parts = [
                f"{character.name}（{character.role or 'unknown'}）状态={character.current_status or 'unknown'}",
            ]
            if character.current_realm:
                parts.append(f"境界={_clean_outline_text(character.current_realm, 40)}")
            if character.faction:
                parts.append(f"阵营={_clean_outline_text(character.faction, 40)}")
            if character.arc:
                parts.append(f"弧线={_clean_outline_text(character.arc, 180)}")
            if stages:
                parts.append(f"阶段={stages}")
            lines.append("- " + " | ".join(parts))
        sections.append("【人物状态与弧线】\n" + "\n".join(lines))

    if storylines:
        lines = []
        for storyline in storylines[:12]:
            beats = _format_json_list(storyline.key_beats, max_items=3)
            parts = [
                f"{storyline.name}（{storyline.line_type or 'unknown'}/{storyline.status or 'unknown'}）",
            ]
            if storyline.core_conflict:
                parts.append(f"冲突={_clean_outline_text(storyline.core_conflict, 140)}")
            if storyline.resolution_direction:
                parts.append(f"解决方向={_clean_outline_text(storyline.resolution_direction, 140)}")
            if beats:
                parts.append(f"节拍={beats}")
            lines.append("- " + " | ".join(parts))
        sections.append("【故事线进度】\n" + "\n".join(lines))

    if power_systems:
        lines = []
        for system in power_systems[:6]:
            levels = _format_json_list(system.levels, max_items=5)
            parts = [system.name]
            if system.description:
                parts.append(f"定位={_clean_outline_text(system.description, 140)}")
            if system.breakthrough_condition:
                parts.append(f"突破={_clean_outline_text(system.breakthrough_condition, 120)}")
            if levels:
                parts.append(f"境界={levels}")
            lines.append("- " + " | ".join(parts))
        sections.append("【力量体系】\n" + "\n".join(lines))

    if factions:
        lines = []
        for faction in factions[:10]:
            parts = [f"{faction.name}（{faction.alignment or 'unknown'}）"]
            if faction.strength_level:
                parts.append(f"实力={_clean_outline_text(faction.strength_level, 80)}")
            if faction.goals:
                parts.append(f"目标={_clean_outline_text(faction.goals, 140)}")
            if faction.secrets:
                parts.append(f"秘密={_clean_outline_text(faction.secrets, 120)}")
            lines.append("- " + " | ".join(parts))
        sections.append("【势力格局】\n" + "\n".join(lines))

    if items:
        lines = []
        for item in items[:12]:
            parts = [f"{item.name}（{item.rarity or 'unknown'}/{item.status or 'unknown'}）"]
            if item.story_significance:
                parts.append(f"意义={_clean_outline_text(item.story_significance, 160)}")
            if item.effects:
                parts.append(f"效果={_clean_outline_text(item.effects, 100)}")
            if item.limitations:
                parts.append(f"限制={_clean_outline_text(item.limitations, 100)}")
            lines.append("- " + " | ".join(parts))
        sections.append("【核心道具】\n" + "\n".join(lines))

    if skills:
        lines = []
        for skill in skills[:10]:
            parts = [f"{skill.name}（{skill.skill_type or 'unknown'}/{skill.grade or 'unknown'}）"]
            if skill.effects:
                parts.append(f"效果={_clean_outline_text(skill.effects, 100)}")
            if skill.limitations:
                parts.append(f"限制={_clean_outline_text(skill.limitations, 100)}")
            lines.append("- " + " | ".join(parts))
        sections.append("【关键技能】\n" + "\n".join(lines))

    if foreshadows:
        lines = []
        for foreshadow in foreshadows[:16]:
            code = foreshadow.code or "未编号"
            parts = [
                f"{code}：{foreshadow.title}（{foreshadow.status or 'unknown'}，优先级{foreshadow.priority or '-'}）",
            ]
            if foreshadow.planned_resolve_chapter:
                parts.append(f"预计第{foreshadow.planned_resolve_chapter}章处理")
            if foreshadow.description:
                parts.append(_clean_outline_text(foreshadow.description, 160))
            lines.append("- " + " | ".join(parts))
        sections.append("【伏笔台账】\n" + "\n".join(lines))

    return "\n\n".join(sections)
