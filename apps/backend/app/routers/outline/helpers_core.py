"""大纲路由共享工具函数（质检、幂等签名、卷线上下文等）。

由 ``routes_main`` 引用；不包含 FastAPI Router 定义。
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Any, Awaitable, Callable, List, Literal, Optional
from uuid import UUID
import json
import re

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Character,
    Faction,
    Foreshadow,
    Item,
    OutlineNode,
    OutlineRevision,
    PowerSystem,
    Project,
    Skill,
    StoryLine,
    WorldSetting,
)
from app.models.chapter import Chapter
from app.schemas import OutlineNodeCreate, OutlineNodeUpdate, OutlineNodeOut
from app.services.xuanhuan_lexicon import (
    MODERN_BLACKLIST_FOR_XUANHUAN,
    is_xuanhuan_like_genre as _is_xuanhuan_like_genre,
)
from app.services.outline_planning import (
    TARGET_CHAPTERS_PER_VOLUME,
    TARGET_WORDS_PER_CHAPTER,
    normalize_volume_plan,
)
from app.services.workflow_graph import WorkflowGraph, WorkflowNode, workflow_runs
from app.utils.chapter_numbering import display_chapter_number, normalize_chapter_plan_title
def build_tree(nodes: List[OutlineNode]) -> List[OutlineNodeOut]:
    """把扁平列表组装成嵌套树（所有层级均按 sort_order 排序）"""
    node_map = {str(n.id): OutlineNodeOut.model_validate(n) for n in nodes}
    # model_validate(from_attributes) 会带入 SQLAlchemy 已加载的 children；
    # 若再按 parent_id 挂接，同一子节点会出现两次（卷下两篇、章重复等）。
    for node_out in node_map.values():
        node_out.children.clear()
    roots = []
    for node_out in node_map.values():
        if node_out.parent_id is None:
            roots.append(node_out)
        else:
            parent = node_map.get(str(node_out.parent_id))
            if parent:
                parent.children.append(node_out)

    def sort_recursive(node_list: list) -> None:
        node_list.sort(key=lambda x: x.sort_order)
        for n in node_list:
            if n.children:
                sort_recursive(n.children)

    sort_recursive(roots)
    return roots


def _clean_outline_text(value: object, limit: int = 120) -> str:
    return " ".join(str(value or "").split())[:limit]


def _sanitize_xuanhuan_outline_text(text: str) -> str:
    cleaned = text
    replacements = [
        ("首席工程师", "大阵主祭"),
        ("AI化", "傀儡化"),
        ("人工智能", "灵智禁制"),
        ("AI", "灵智"),
        ("半机械", "半傀"),
        ("机械", "机关"),
        ("芯片", "命纹碎片"),
        ("量子", "微尘"),
        ("基因实验室", "血脉禁室"),
        ("星际文明", "诸天古域"),
        ("星际", "诸天"),
        ("程序上传", "神识刻印"),
        ("控制台", "阵枢石台"),
    ]
    for src, dst in replacements:
        cleaned = cleaned.replace(src, dst)
    return cleaned


def _sanitize_generated_outline_chapter(chapter: dict, genre: str | None) -> dict:
    if not _is_xuanhuan_like_genre(genre):
        return chapter
    sanitized = dict(chapter)
    for field in ("title", "opening_hook", "core_event", "character_change", "foreshadow", "end_hook"):
        value = sanitized.get(field)
        if isinstance(value, str) and value:
            sanitized[field] = _sanitize_xuanhuan_outline_text(value)
    return sanitized


def _outline_batch_size(model_profile: str) -> int:
    return 30 if model_profile == "gemini" else 15


def _format_previous_chapters_context(chapters: list[dict], max_items: int = 10) -> str:
    if not chapters:
        return ""

    lines = []
    for chapter in chapters[-max_items:]:
        number = chapter.get("number") or "?"
        title = _clean_outline_text(chapter.get("title"), 40) or "未命名"
        core_event = _clean_outline_text(chapter.get("core_event"), 120)
        character_change = _clean_outline_text(chapter.get("character_change"), 100)
        foreshadow = _clean_outline_text(chapter.get("foreshadow"), 100)
        end_hook = _clean_outline_text(chapter.get("end_hook"), 120)
        lines.append(
            f"第{number}章：{title} | 核心事件：{core_event} | 人物变化：{character_change} | "
            f"伏笔：{foreshadow} | 章末钩子：{end_hook}"
        )
    return "\n".join(lines)


def _collect_protagonist_anchor_names(characters) -> list[str]:
    """主角姓名 + 别名，用于境界归因扫描（去重保序）。"""
    anchors: list[str] = []
    for char in characters or []:
        if getattr(char, "role", None) != "protagonist":
            continue
        name = getattr(char, "name", None)
        if isinstance(name, str) and name.strip():
            anchors.append(name.strip())
        raw_aliases = getattr(char, "alias", None) or []
        if isinstance(raw_aliases, list):
            for a in raw_aliases:
                if isinstance(a, str) and a.strip():
                    anchors.append(a.strip())
    return list(dict.fromkeys(anchors))


def _protagonist_realm_attributed(
    text: str,
    realm_name: str,
    protagonist_names: list[str],
    *,
    max_span: int = 56,
) -> bool:
    """
    判断 text 中的 realm_name 是否应计作「主角境界描写」。
    要求：与任一主角姓名/别名（或「主角」）同处一段短跨度内，且出现修为归因信号
    （突破/晋升/以X境/从X境 等），避免「林烬遭遇灵王境强敌」把灵王境记成主角境界。
    """
    anchors = [n for n in protagonist_names if isinstance(n, str) and n.strip()]
    if not anchors:
        return True
    anchors = list(dict.fromkeys([*anchors, "主角"]))
    for pname in anchors:
        p_start = 0
        while True:
            p = text.find(pname, p_start)
            if p == -1:
                break
            r_start = 0
            while True:
                r = text.find(realm_name, r_start)
                if r == -1:
                    break
                lo = min(p, r)
                hi = max(p + len(pname), r + len(realm_name))
                if hi - lo > max_span:
                    r_start = r + 1
                    continue
                mid = text[lo:hi]
                if any(v in mid for v in PROTAGONIST_REALM_ATTRIBUTION_VERBS):
                    return True
                if f"以{realm_name}" in mid or f"从{realm_name}" in mid:
                    return True
                r_start = r + 1
            p_start = p + 1
    return False


def _extract_max_realm_from_chapters(
    chapters: list[dict],
    name_to_rank: dict[str, int],
    protagonist_names: list[str] | None = None,
) -> tuple[int | None, str | None]:
    """从已生成章节列表中扫描 character_change，提取主角出现过的最高境界 rank 及对应名称。"""
    max_rank: int | None = None
    max_realm: str | None = None
    rank_to_name = {v: k for k, v in name_to_rank.items()}
    for chapter in chapters:
        rank = _extract_protagonist_realm_rank(
            chapter, name_to_rank, protagonist_names=protagonist_names
        )
        if rank is not None and (max_rank is None or rank > max_rank):
            max_rank = rank
            max_realm = rank_to_name.get(rank, str(rank))
    return max_rank, max_realm


def _format_rolling_continuity_state(
    chapters: list[dict],
    protagonist_max_rank: int | None = None,
    protagonist_max_realm: str | None = None,
) -> str:
    if not chapters:
        return ""

    last = chapters[-1]
    last_number = last.get("number") or "?"
    last_title = _clean_outline_text(last.get("title"), 40) or "未命名"
    last_hook = _clean_outline_text(last.get("end_hook"), 160) or "（上一批未给出章末钩子）"

    recent_foreshadows = [
        _clean_outline_text(chapter.get("foreshadow"), 120)
        for chapter in chapters[-8:]
        if _clean_outline_text(chapter.get("foreshadow"), 120)
    ]
    recent_events = [
        _clean_outline_text(chapter.get("core_event"), 120)
        for chapter in chapters[-6:]
        if _clean_outline_text(chapter.get("core_event"), 120)
    ]

    lines = [
        f"上一批最后章节：第{last_number}章《{last_title}》",
        f"下一批开篇必须承接：{last_hook}",
    ]
    if recent_foreshadows:
        lines.append(f"未回收/待处理伏笔：{'；'.join(recent_foreshadows)}")
    if recent_events:
        lines.append(f"不得重复已发生的核心事件：{'；'.join(recent_events)}")
    if protagonist_max_rank is not None:
        realm_label = f"{protagonist_max_realm}（rank{protagonist_max_rank}）" if protagonist_max_realm else f"rank{protagonist_max_rank}"
        lines.append(
            f"【主角境界硬约束】已达最高境界：{realm_label}。"
            "若本批出现境界回落，必须在 character_change 明确交代原因"
            "（封印触发/重创透支/异界压制/反噬代价/主动隐匿之一），否则视为逻辑断层。"
        )
    return "\n".join(lines)


def _format_book_quality_continuity_state(chapters: list[dict]) -> str:
    """
    Book-level outline QA receives all target chapter plans as the object under review.
    It must not recycle those same plans into the "already happened" rolling ledger.
    """
    chapter_count = len(chapters)
    return (
        f"全书质检不使用滚动连续性账本：当前 {chapter_count} 个章节计划全部属于待检对象，"
        "不得把待检章节自身当作已发生事实来判定重复。"
    )


def _format_outline_batch_goal(
    node_title: str,
    batch_offset: int,
    batch_count: int,
    planned_chapters: int,
    node_generated_chapters: int | None = None,
) -> str:
    global_start = batch_offset + 1
    global_end = batch_offset + batch_count
    local_done = batch_offset if node_generated_chapters is None else node_generated_chapters
    local_start = local_done + 1
    local_end = local_done + batch_count
    return (
        f"本批生成全书第{global_start}-{global_end}章，也是《{node_title}》本卷第{local_start}-{local_end}章；"
        f"《{node_title}》共{planned_chapters}章。本批要承接已有章节，不得重启本卷冲突或提前透支后续卷爆点。"
    )


def _format_outline_word_budget_context(
    *,
    target_words: int | None,
    chapter_count: int,
    chapter_word_target: int = TARGET_WORDS_PER_CHAPTER,
    scope_label: str = "全书",
) -> str:
    estimated_words = max(0, chapter_count) * chapter_word_target
    lines = [
        f"{scope_label}当前章节数：{chapter_count} 章",
        f"{scope_label}按每章约{chapter_word_target}字估算：约{estimated_words}字",
    ]
    if target_words and target_words > 0:
        gap = target_words - estimated_words
        gap_label = f"+{gap}" if gap >= 0 else str(gap)
        lines.append(f"{scope_label}目标总字数：{target_words}字（差值：{gap_label}字）")
    else:
        lines.append(f"{scope_label}目标总字数：未设置（建议在项目中设定 target_words）")
    lines.append(
        f"{scope_label}节奏要求：禁止后期跨位面速刷；必须保证中后期仍有足够章节承载势力升级、人物代价、伏笔回收与终局铺垫。"
    )
    return "\n".join(lines)


def _format_global_outline_context(volume_nodes: list[tuple[OutlineNode, int]]) -> str:
    lines = []
    for idx, (node, planned_chapters) in enumerate(volume_nodes, start=1):
        extra = node.extra if isinstance(node.extra, dict) else {}
        lines.append(
            f"{idx}. 《{node.title}》{planned_chapters}章 | "
            f"摘要：{_clean_outline_text(node.summary, 120)} | "
            f"阶段立意：{_clean_outline_text(extra.get('theme_stage'), 120)} | "
            f"人物弧：{_clean_outline_text(extra.get('character_arc'), 120)} | "
            f"核心悬念：{_clean_outline_text(node.hook, 100)} | "
            f"主要冲突：{_clean_outline_text(node.conflict, 100)}"
        )
    return "\n".join(lines)


def _format_json_list(value: object, max_items: int = 3) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value[:max_items]:
        if isinstance(item, dict):
            chapter_range = _clean_outline_text(item.get("chapter_range"), 24)
            stage = _clean_outline_text(item.get("stage") or item.get("name"), 40)
            state = _clean_outline_text(item.get("state"), 60)
            label = ":".join(part for part in [chapter_range, stage] if part)
            if state:
                label = f"{label}({state})" if label else state
            if label:
                parts.append(label)
        else:
            text = _clean_outline_text(item, 60)
            if text:
                parts.append(text)
    return "、".join(parts)


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


def _chapter_duplicate_signature(chapter: dict) -> tuple[str, str, str] | None:
    core_event = _clean_outline_text(chapter.get("core_event"), 240)
    character_change = _clean_outline_text(chapter.get("character_change"), 220)
    end_hook = _clean_outline_text(chapter.get("end_hook"), 220)
    if not core_event or not (character_change or end_hook):
        return None
    return (core_event, character_change, end_hook)


# 传统修真术语池：当项目自定义的 PowerSystem 不包含这些词时，出现即视为体系漂移。
# 命中时按 critical 处理，要求重写章节大纲。
TRADITIONAL_CULTIVATION_BLACKLIST: set[str] = {
    # 仙侠九境（练气→飞升）
    "练气", "炼气", "筑基", "金丹", "结丹", "元婴", "化神",
    "炼虚", "合体", "大乘", "渡劫", "飞升",
    # 仙人位阶
    "真仙", "天仙", "玄仙", "金仙", "大罗金仙", "罗汉", "菩萨",
    # 斗气大陆体系（来自《斗破苍穹》，作为模仿参考时不应直接照搬术语）
    "斗者", "斗师", "大斗师", "斗灵", "斗王", "斗皇", "斗宗", "斗尊", "斗圣", "斗帝",
    # 完美世界/遮天体系
    "搬血", "洞天", "化灵", "铸神",
    # 武道
    "宗师境", "大宗师", "武圣", "武神",
}

# 在 character_change 中出现这些词时，视为已交代境界跌落/重伤的合理代价，跳过回退告警。
REALM_REGRESSION_TRIGGER_WORDS: set[str] = {
    "跌落", "重伤", "被封", "废功", "重创", "反噬", "失去修为",
    "境界跌落", "修为尽失", "被封印", "受重创", "走火入魔",
    "境界倒退", "修为跌落", "压制", "副作用", "代价", "透支",
    "封印", "燃烧寿元", "烧寿命", "夺舍",
}

# 与主角指代共现时：命中其一才认定该境界在写「主角修为」，避免把敌对/传闻中的
# 高阶境界误算进 running_max，造成后续章节的假阳性「无解释境界倒退」。
PROTAGONIST_REALM_ATTRIBUTION_VERBS: tuple[str, ...] = (
    "突破", "晋升", "踏入", "达到", "晋入", "跨入", "迈入",
    "升至", "已至", "臻至", "巩固", "稳固", "回落", "跌落", "退回",
    "停留", "修为", "境界", "一举突破", "成功突破",
    "惟有", "只有", "仍是", "还是", "下滑", "跌回", "降回",
    "压制", "自封", "压住",
)

# 角色死亡 / 永久退场标记词；命中即视为该章节宣告该角色离场。
CHARACTER_DEATH_MARKERS: set[str] = {
    "牺牲", "殒落", "陨落", "阵亡", "身死", "去世", "死亡",
    "魂飞魄散", "自毁", "同归于尽", "暴毙", "猝死", "战死",
    "身殒", "殉道", "献祭", "永镇", "魂消", "魂灭",
}

# 死亡后再次出场的合理回收机制。命中其一视为已交代复活/化身/假死。
CHARACTER_REVIVAL_TRIGGERS: set[str] = {
    "归来", "重生", "复活", "苏醒", "神魂", "残识", "寄宿",
    "化身", "分身", "虚影", "假死", "重塑", "复苏",
    "夺舍", "转世", "魂归", "执念", "藏身", "潜伏",
    "残魂", "魂魄", "传承", "意志", "回光返照",
}

# 角色"主动登场"信号词；在角色名附近命中说明该章里有该角色的实际行动。
CHARACTER_ACTIVE_APPEARANCE_VERBS: set[str] = {
    "送来", "送给", "送出", "提供", "告诉", "告知", "出手",
    "现身", "登场", "援助", "救下", "保护", "联手",
    "传授", "交给", "递给", "示警", "嘱咐", "说道",
    "解释", "出现在", "回来", "重返", "出关",
}

# 自我决定型主题指纹：项目主题包含其中任一关键词时视为「凡人逆袭」类立意，
# 此时不应该用「天选血脉/完美炉胎」等设定为主角强大背书。
SELF_DETERMINATION_THEME_KEYWORDS: set[str] = {
    "我命由我", "我命", "凡人", "草根", "自律", "苦修", "苦练",
    "逆袭", "后天突破", "后天", "不靠天赋", "不靠血脉",
    "白手起家", "平凡", "普通人",
}

# 反主题揭露：把主角强大归因于「被选中/血脉/天命/转世」的设定。
# 仅在主题为自我决定型时才视为冲突。
DESTINY_REVEAL_PATTERNS: set[str] = {
    "完美炉胎", "完美载体", "完美容器", "天选之子", "天选之人",
    "天命之人", "命定之人", "选中", "选定",
    "血脉觉醒", "神血", "上古血脉", "帝者血脉", "古神血脉",
    "神族后裔", "古神后裔", "圣血",
    "天命", "宿命", "注定", "命中注定",
    "转世重生", "真神转世", "古神转世", "上古真灵",
    "先天道体", "先天圣体", "万年灵根", "万古一帝", "天纵之资",
    "炉胎", "载体", "实验体", "试验体",
}

# 强主角指代标记：仅当 protagonist_names 不可用时使用的回退指代词。
# 故意比较窄，避免命中 NPC 真相揭露（如「圣塔少主原来是炉胎」）。
PROTAGONIST_CONTEXT_HINTS: set[str] = {
    "主角", "他本是", "他原本", "他实际", "他真正", "他乃是",
    "他天生其实",
}


def _collect_power_system_whitelist(power_systems) -> set[str]:
    """从所有 PowerSystem.levels 抽取合法境界名（含去掉「境」后缀的简写）。"""
    whitelist: set[str] = set()
    for system in power_systems or []:
        name = (getattr(system, "name", None) or "").strip()
        if name:
            whitelist.add(name)
        levels = getattr(system, "levels", None)
        if not isinstance(levels, list):
            continue
        for level in levels:
            if not isinstance(level, dict):
                continue
            level_name = (level.get("name") or "").strip()
            if not level_name:
                continue
            whitelist.add(level_name)
            if level_name.endswith("境") and len(level_name) > 1:
                whitelist.add(level_name[:-1])
    return whitelist


def _build_realm_rank_map(power_systems) -> tuple[dict[str, int], int | None, int | None]:
    """构造 {境界名: rank} 映射，并返回 (map, max_system_rank, declared_protagonist_end_rank)."""
    name_to_rank: dict[str, int] = {}
    max_rank = 0
    end_rank: int | None = None
    for system in power_systems or []:
        levels = getattr(system, "levels", None)
        if isinstance(levels, list):
            for level in levels:
                if not isinstance(level, dict):
                    continue
                level_name = (level.get("name") or "").strip()
                rank = level.get("rank")
                if not level_name or not isinstance(rank, int) or rank <= 0:
                    continue
                if level_name not in name_to_rank or rank > name_to_rank[level_name]:
                    name_to_rank[level_name] = rank
                if level_name.endswith("境") and len(level_name) > 1:
                    bare = level_name[:-1]
                    if bare not in name_to_rank or rank > name_to_rank[bare]:
                        name_to_rank[bare] = rank
                if rank > max_rank:
                    max_rank = rank
        declared = getattr(system, "protagonist_end_rank", None)
        if isinstance(declared, int) and declared > 0:
            end_rank = max(end_rank or 0, declared)
    return name_to_rank, (max_rank or None), end_rank


def _scan_banned_terms(text: str, banned: set[str]) -> set[str]:
    if not text:
        return set()
    return {term for term in banned if term and term in text}


def _detect_outline_terminology_issues(
    chapters: list[dict],
    *,
    power_systems,
    genre: str = "",
) -> list[dict]:
    """
    扫描章节大纲文本，识别两类术语脱轨：
      1. 项目 PowerSystem 之外的传统修真术语（critical）。
      2. 玄幻题材下的现代/科幻词汇（critical）。
    """
    if power_systems is None:
        return []
    whitelist = _collect_power_system_whitelist(power_systems)
    cultivation_pool = {term for term in TRADITIONAL_CULTIVATION_BLACKLIST if term not in whitelist}
    is_xuanhuan = _is_xuanhuan_like_genre(genre)
    modern_pool = MODERN_BLACKLIST_FOR_XUANHUAN if is_xuanhuan else set()

    if not cultivation_pool and not modern_pool:
        return []

    issues: list[dict] = []
    whitelist_label = "、".join(sorted(whitelist)) if whitelist else "（项目尚未配置力量体系）"

    for chapter in chapters:
        number = chapter.get("number")
        if not isinstance(number, int):
            continue
        text_blob = " | ".join(
            str(chapter.get(field, ""))
            for field in ("title", "opening_hook", "core_event", "character_change", "foreshadow", "end_hook")
        )
        cultivation_hits = sorted(_scan_banned_terms(text_blob, cultivation_pool))
        modern_hits = sorted(_scan_banned_terms(text_blob, modern_pool))

        if cultivation_hits:
            issues.append({
                "severity": "critical",
                "type": "continuity",
                "chapter_numbers": [number],
                "description": (
                    f"第{number}章使用了项目力量体系外的修真术语：{'、'.join(cultivation_hits)}。"
                    f"项目实际境界白名单：{whitelist_label[:160]}。"
                    "需替换为项目自定义境界，否则破坏世界观一致性，连锁影响后续卷设定。"
                ),
                "suggested_patch": {
                    "chapter_number": number,
                    "field": "core_event",
                    "replacement": "",
                },
            })
        if modern_hits:
            issues.append({
                "severity": "critical",
                "type": "continuity",
                "chapter_numbers": [number],
                "description": (
                    f"第{number}章在玄幻/仙侠题材下出现现代/科幻词汇：{'、'.join(modern_hits)}。"
                    "需改写为东方玄幻意象（阵法中枢、古禁制、神纹、天机枢纽、血脉禁室等）。"
                ),
                "suggested_patch": {
                    "chapter_number": number,
                    "field": "core_event",
                    "replacement": "",
                },
            })
    return issues


def _extract_protagonist_realm_rank(
    chapter: dict,
    name_to_rank: dict[str, int],
    *,
    protagonist_names: list[str] | None = None,
) -> int | None:
    """
    仅扫描 character_change 字段（描述「谁的认知/处境/关系发生变化」），
    返回该章节中计作「主角修为」的境界里最大的 rank。

    当传入 protagonist_names（非空）时，仅统计与主角姓名/「主角」共现且带修为归因
    语境的境界名，避免敌对/传闻中的高阶境界抬高 running_max 导致假阳性回退告警。
    未传或为空列表时保持旧行为：取文中出现的白名单境界最大 rank（兼容无人物卡的质检）。
    """
    text = str(chapter.get("character_change") or "")
    if not text or not name_to_rank:
        return None
    use_attribution = bool(protagonist_names)
    found_rank: int | None = None
    for realm_name, rank in name_to_rank.items():
        if not realm_name or realm_name not in text:
            continue
        if use_attribution and not _protagonist_realm_attributed(
            text, realm_name, protagonist_names or [],
        ):
            continue
        if found_rank is None or rank > found_rank:
            found_rank = rank
    return found_rank


def _realm_display_name_for_rank(rank: int, name_to_rank: dict[str, int]) -> str:
    """同一 rank 可能对应全名与简写，优先展示带「境」的较长名称。"""
    candidates = [n for n, r in name_to_rank.items() if r == rank]
    if not candidates:
        return f"rank{rank}"
    with_jing = [n for n in candidates if isinstance(n, str) and n.endswith("境")]
    pool = with_jing if with_jing else candidates
    return max(pool, key=len)


# 与 ai.chapter_debrief 写入保持一致（正文复盘提交时追加主角境界快照）
DEBRIEF_REALM_MILESTONES_EXTRA_KEY = "debrief_realm_milestones"


def _rank_for_realm_label(label: str, name_to_rank: dict[str, int]) -> int | None:
    """从自由文本境界名解析 rank；优先精确匹配，其次命中子串的最长境界名。"""
    if not label or not name_to_rank:
        return None
    s = label.strip()
    if s in name_to_rank:
        return name_to_rank[s]
    best: int | None = None
    best_len = 0
    for name, r in name_to_rank.items():
        if not isinstance(name, str) or not name:
            continue
        if name in s and len(name) >= best_len:
            if best is None or r >= best:
                best = r
                best_len = len(name)
    return best


def merge_outline_and_debrief_realm_milestones(
    outline_milestones: list[dict[str, Any]],
    debrief_rows: list[dict[str, Any]],
    name_to_rank: dict[str, int],
) -> list[dict[str, Any]]:
    """
    合并大纲「人物变化」里程碑与正文复盘提交时记录的主角境界快照，
    按章取各源中最高 rank，再全书扫一遍只保留「创新高」节点。
    """
    events: list[dict[str, Any]] = []
    for m in outline_milestones:
        events.append(
            {
                "chapter_number": int(m["chapter_number"]),
                "chapter_title": str(m.get("chapter_title") or ""),
                "realm_name": str(m.get("realm_name") or ""),
                "realm_rank": int(m["realm_rank"]),
                "character_change": str(m.get("character_change") or ""),
                "source": "outline",
            }
        )
    for d in debrief_rows:
        if not isinstance(d, dict):
            continue
        ch = d.get("chapter_number")
        if not isinstance(ch, int):
            try:
                ch = int(ch)
            except (TypeError, ValueError):
                continue
        raw_name = str(d.get("realm_name") or "").strip()
        rr = d.get("realm_rank")
        if isinstance(rr, bool) or rr is None:
            resolved = _rank_for_realm_label(raw_name, name_to_rank) if name_to_rank else None
            rr = resolved if resolved is not None else 0
        else:
            try:
                rr = int(rr)
            except (TypeError, ValueError):
                rr = _rank_for_realm_label(raw_name, name_to_rank) or 0
        if rr <= 0 and not raw_name:
            continue
        if rr <= 0 and name_to_rank:
            resolved = _rank_for_realm_label(raw_name, name_to_rank)
            if resolved is not None:
                rr = resolved
        disp = raw_name
        if name_to_rank and rr > 0:
            disp = _realm_display_name_for_rank(rr, name_to_rank)
        elif not disp and rr > 0:
            disp = _realm_display_name_for_rank(rr, name_to_rank)
        events.append(
            {
                "chapter_number": ch,
                "chapter_title": str(d.get("chapter_title") or "")[:400],
                "realm_name": disp or raw_name or f"rank{rr}",
                "realm_rank": rr,
                "character_change": "正文复盘 character_updates",
                "source": "debrief",
            }
        )

    if not events:
        return []

    by_ch: dict[int, list[dict[str, Any]]] = {}
    for e in events:
        ch = int(e["chapter_number"])
        by_ch.setdefault(ch, []).append(e)

    per_chapter: list[tuple[int, dict[str, Any], int]] = []
    for ch in sorted(by_ch.keys()):
        group = by_ch[ch]
        best: dict[str, Any] | None = None
        best_rank = -1
        for e in group:
            r = int(e.get("realm_rank") or 0)
            if r > best_rank:
                best_rank = r
                best = dict(e)
            elif r == best_rank and best is not None:
                if e.get("source") == "debrief" and best.get("source") != "debrief":
                    best = dict(e)
        if best is not None:
            per_chapter.append((ch, best, best_rank))

    running = 0
    prev_debrief_name = ""
    merged: list[dict[str, Any]] = []
    for ch, best, r in per_chapter:
        nm = str(best.get("realm_name") or "").strip()
        if name_to_rank:
            if r <= running:
                continue
            running = r
            merged.append(
                {
                    "chapter_number": ch,
                    "chapter_title": best.get("chapter_title") or "",
                    "realm_name": nm or _realm_display_name_for_rank(r, name_to_rank),
                    "realm_rank": r,
                    "character_change": str(best.get("character_change") or ""),
                    "source": str(best.get("source") or "outline"),
                }
            )
        else:
            if r > running:
                running = r
                merged.append(
                    {
                        "chapter_number": ch,
                        "chapter_title": best.get("chapter_title") or "",
                        "realm_name": nm or f"rank{r}",
                        "realm_rank": r,
                        "character_change": str(best.get("character_change") or ""),
                        "source": str(best.get("source") or "outline"),
                    }
                )
            elif nm and nm != prev_debrief_name:
                prev_debrief_name = nm
                merged.append(
                    {
                        "chapter_number": ch,
                        "chapter_title": best.get("chapter_title") or "",
                        "realm_name": nm,
                        "realm_rank": 0,
                        "character_change": str(best.get("character_change") or ""),
                        "source": str(best.get("source") or "outline"),
                    }
                )

    return merged


def build_protagonist_realm_timeline(
    chapter_contexts: list[dict],
    power_systems,
    *,
    protagonist_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    从章节计划的 character_change 聚合主角境界「创新高」节点（与战力曲线质检同源归因）。
    数据源为已入库的大纲 chapter_plan；无力量体系 levels 时无法解析境界名。
    """
    name_to_rank, _, _ = _build_realm_rank_map(power_systems)
    if not name_to_rank:
        return {
            "has_realm_whitelist": False,
            "anchored": bool(protagonist_names),
            "chapter_plans_scanned": 0,
            "milestones": [],
        }
    anchors = [n for n in (protagonist_names or []) if isinstance(n, str) and n.strip()]
    use_names: list[str] | None = anchors if anchors else None

    sorted_chapters = sorted(
        (c for c in chapter_contexts if isinstance(c.get("number"), int)),
        key=lambda c: int(c["number"]),
    )
    running = 0
    milestones: list[dict[str, Any]] = []
    for ch in sorted_chapters:
        rank = _extract_protagonist_realm_rank(ch, name_to_rank, protagonist_names=use_names)
        if rank is None or rank <= running:
            continue
        running = rank
        realm_label = _realm_display_name_for_rank(rank, name_to_rank)
        cc = str(ch.get("character_change") or "")
        milestones.append(
            {
                "chapter_number": int(ch["number"]),
                "chapter_title": str(ch.get("title") or ""),
                "realm_name": realm_label,
                "realm_rank": rank,
                "character_change": cc[:400],
            }
        )

    return {
        "has_realm_whitelist": True,
        "anchored": bool(anchors),
        "chapter_plans_scanned": len(sorted_chapters),
        "milestones": milestones,
    }


def _detect_outline_power_curve_issues(
    chapters: list[dict],
    *,
    power_systems,
    scope: str = "volume",
    protagonist_names: list[str] | None = None,
) -> list[dict]:
    """
    战力曲线确定性校验：
      1. 主角境界回落 ≥ 2 级 但 character_change 未交代代价 → high。
      2. 在书级范围下，主角已抵达终点境界但剩余章节 > 25%（且总章 > 60）→ high pacing。
    """
    if not power_systems:
        return []
    name_to_rank, max_system_rank, declared_end_rank = _build_realm_rank_map(power_systems)
    if not name_to_rank:
        return []

    sorted_chapters = sorted(
        [c for c in chapters if isinstance(c.get("number"), int)],
        key=lambda c: c["number"],
    )
    total_chapters = len(sorted_chapters)
    if total_chapters == 0:
        return []

    issues: list[dict] = []
    running_max = 0
    last_peak_chapter: int | None = None
    for chapter in sorted_chapters:
        rank = _extract_protagonist_realm_rank(
            chapter, name_to_rank, protagonist_names=protagonist_names,
        )
        if rank is None:
            continue
        number = chapter["number"]
        change_text = str(chapter.get("character_change") or "")
        has_trigger = any(trig in change_text for trig in REALM_REGRESSION_TRIGGER_WORDS)
        if rank + 2 <= running_max and not has_trigger:
            issues.append({
                "severity": "high",
                "type": "continuity",
                "chapter_numbers": [number],
                "description": (
                    f"第{number}章主角境界回落到 rank{rank}（character_change 提及），"
                    f"但前文最高已达 rank{running_max}，本章未在 character_change 交代"
                    "跌落/重伤/反噬/封印/透支寿元等代价机制，属于无解释的境界倒退。"
                ),
                "suggested_patch": {
                    "chapter_number": number,
                    "field": "character_change",
                    "replacement": "",
                },
            })
        if rank > running_max:
            running_max = rank
            last_peak_chapter = number

    if scope == "book" and last_peak_chapter is not None and total_chapters >= 60:
        target_end_rank = declared_end_rank if declared_end_rank else max_system_rank
        if target_end_rank and running_max >= target_end_rank:
            remaining = total_chapters - last_peak_chapter
            remaining_ratio = remaining / total_chapters if total_chapters else 0
            if remaining_ratio > 0.25:
                issues.append({
                    "severity": "high",
                    "type": "pacing",
                    "chapter_numbers": [last_peak_chapter],
                    "description": (
                        f"第{last_peak_chapter}章主角境界已达 rank{running_max}"
                        f"（接近/达到终点 rank{target_end_rank}），但全书剩余 {remaining} 章"
                        f"（约 {remaining_ratio:.0%}），后期境界提升空间已耗尽，"
                        "必然导致跨地图速刷或重复刷怪。建议放缓中段境界推进，"
                        "或在大纲规划层（plan_full_structure）扩展终点境界与卷数。"
                    ),
                    "suggested_patch": {
                        "chapter_number": last_peak_chapter,
                        "field": "core_event",
                        "replacement": "",
                    },
                })

    return issues


def _name_near_marker(text: str, name: str, markers, window: int = 18) -> bool:
    """检查 text 中 name 出现位置 ±window 字符内是否有任一 marker。"""
    if not name or not text:
        return False
    pos = 0
    while True:
        i = text.find(name, pos)
        if i == -1:
            return False
        snippet = text[max(0, i - window): i + len(name) + window]
        for m in markers:
            if m and m in snippet:
                return True
        pos = i + len(name)


def _collect_character_aliases(characters) -> dict[str, str]:
    """构造 {name_or_alias: canonical_name} 映射；按长度降序排序便于后续优先匹配长名。"""
    name_to_canonical: dict[str, str] = {}
    for char in characters or []:
        canonical = (getattr(char, "name", None) or "").strip()
        if not canonical:
            continue
        name_to_canonical[canonical] = canonical
        aliases = getattr(char, "alias", None)
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str):
                    a = alias.strip()
                    if a and a not in name_to_canonical:
                        name_to_canonical[a] = canonical
    return name_to_canonical


def _detect_outline_character_death_continuity(
    chapters: list[dict],
    *,
    characters,
) -> list[dict]:
    """
    检测角色死亡后无机制再次主动登场。
    判断流程（按章节顺序）：
      1. 章节文本中角色名 ±18 字符内出现死亡词 → 标记该角色为已宣告死亡。
      2. 已宣告死亡的角色，若后续章节出现复活类触发词 → 视为机制说明，重置警戒。
      3. 已宣告死亡且未交代复活时，再次出现主动登场动词 → critical issue。
    仅扫描 core_event/character_change/end_hook 等剧情字段，不扫描 foreshadow（伏笔
    可以提及死者而不构成实际登场）。
    """
    if not characters:
        return []
    name_to_canonical = _collect_character_aliases(characters)
    if not name_to_canonical:
        return []

    sorted_chapters = sorted(
        [c for c in chapters if isinstance(c.get("number"), int)],
        key=lambda c: c["number"],
    )

    death_state: dict[str, int] = {}     # canonical -> first death chapter
    explained_after: dict[str, int] = {}  # canonical -> chapter where revival explained
    issues: list[dict] = []
    seen_pair: set[tuple[str, int]] = set()

    # 长名优先匹配，避免 "鬼手长老" 命中 "鬼手"
    sorted_names = sorted(name_to_canonical.keys(), key=len, reverse=True)

    for chapter in sorted_chapters:
        number = chapter["number"]
        text_blob = " | ".join(
            str(chapter.get(field, ""))
            for field in ("title", "opening_hook", "core_event", "character_change", "end_hook")
        )
        if not text_blob:
            continue

        for raw_name in sorted_names:
            canonical = name_to_canonical[raw_name]
            if raw_name not in text_blob:
                continue

            # 1) 死亡宣告
            if canonical not in death_state:
                if _name_near_marker(text_blob, raw_name, CHARACTER_DEATH_MARKERS, window=22):
                    death_state[canonical] = number
                continue

            # 2) 已死亡，本章是否给出复活机制
            if canonical not in explained_after:
                if _name_near_marker(text_blob, raw_name, CHARACTER_REVIVAL_TRIGGERS, window=22):
                    explained_after[canonical] = number
                    continue
                # 3) 检测主动登场
                if _name_near_marker(text_blob, raw_name, CHARACTER_ACTIVE_APPEARANCE_VERBS, window=14):
                    pair_key = (canonical, number)
                    if pair_key in seen_pair:
                        continue
                    seen_pair.add(pair_key)
                    issues.append({
                        "severity": "critical",
                        "type": "continuity",
                        "chapter_numbers": [death_state[canonical], number],
                        "description": (
                            f"《{canonical}》在第{death_state[canonical]}章被宣告死亡/殒落/自毁，"
                            f"但在第{number}章再次主动登场（提供道具/援助/现身/出手），"
                            "且本章未交代复活、神魂寄宿、假死、化身、传承等机制；属于角色生死逻辑断层。"
                            "建议在死亡章节加埋[残魂寄宿于X物]或在再现章节明确化身/分身/复苏触发词。"
                        ),
                        "suggested_patch": {
                            "chapter_number": number,
                            "field": "character_change",
                            "replacement": "",
                        },
                    })

    return issues


def _theme_is_self_determination(theme_statement: str, premise: str = "") -> bool:
    """判断项目主题是否属于「凡人逆袭」类。"""
    blob = f"{theme_statement or ''} || {premise or ''}"
    if not blob.strip():
        return False
    return any(kw in blob for kw in SELF_DETERMINATION_THEME_KEYWORDS)


def _detect_outline_theme_alignment_issues(
    chapters: list[dict],
    *,
    theme_statement: str = "",
    premise: str = "",
    protagonist_names: list[str] | None = None,
) -> list[dict]:
    """
    主题对齐校验：当主题属于「凡人逆袭」类时，章节中出现「完美炉胎/天选/血脉觉醒/
    转世重生/帝者血脉/圣体/道体」等揭露 + 主角指代 → medium。

    注意只扫描 core_event 与 character_change（揭露主角真实身份的字段），
    不扫描 foreshadow（埋伏笔可以提及这些词）。
    """
    if not _theme_is_self_determination(theme_statement, premise):
        return []

    sorted_chapters = sorted(
        [c for c in chapters if isinstance(c.get("number"), int)],
        key=lambda c: c["number"],
    )
    if not sorted_chapters:
        return []

    # 主角名片：优先方案（强精度）。未提供时退化为「揭露必须出现在
    # character_change 字段」的回退方案——character_change 通常描述主角变化，
    # 即便提及 NPC 也更可能是与主角相关的弧线节点。
    protagonist_set = {n.strip() for n in (protagonist_names or []) if n and isinstance(n, str)}

    issues: list[dict] = []
    seen_chapters: set[int] = set()

    for chapter in sorted_chapters:
        number = chapter["number"]
        if number in seen_chapters:
            continue
        text_blob = " | ".join(
            str(chapter.get(field, ""))
            for field in ("title", "core_event", "character_change", "end_hook")
        )
        if not text_blob:
            continue

        revealed = sorted(p for p in DESTINY_REVEAL_PATTERNS if p in text_blob)
        if not revealed:
            continue

        if protagonist_set:
            # 强精度：揭露词必须出现在主角名 ±30 字符内
            has_protagonist_marker = any(
                _name_near_marker(text_blob, name, revealed, window=30)
                for name in protagonist_set
            )
        else:
            # 回退：揭露词必须出现在 character_change 字段，或匹配窄主角指代
            char_change_text = str(chapter.get("character_change") or "")
            has_protagonist_marker = (
                any(p in char_change_text for p in revealed)
                or any(hint in text_blob for hint in PROTAGONIST_CONTEXT_HINTS)
            )
        if not has_protagonist_marker:
            continue

        seen_chapters.add(number)
        issues.append({
            "severity": "medium",
            "type": "theme_alignment",
            "chapter_numbers": [number],
            "description": (
                f"第{number}章揭示主角真实身份/起源时使用了「{('、'.join(revealed))[:80]}」类设定，"
                "把主角强大归因于「被选中/血脉/天命」，与「我命由我 / 凡人逆袭 / 草根崛起」"
                "类立意相冲突，会削弱草根爽感。"
                "建议改写为「主角原本是实验残次品 / 被弃用炉胎 / 被否定的载体」，"
                "再以后天苦修把『注定』改写成『逆天』，强化主题。"
            ),
            "suggested_patch": {
                "chapter_number": number,
                "field": "core_event",
                "replacement": "",
            },
        })

    return issues


# ─────────────────────────────────────────────────────────────
#  Foreshadow ledger auditor
# ─────────────────────────────────────────────────────────────

def _detect_outline_foreshadow_issues(
    chapters: list[dict],
    *,
    foreshadows,
) -> list[dict]:
    """
    伏笔台账确定性审计（基于 Foreshadow 表）：
      1. 已过期未回收：status=open + planned_resolve_chapter < 当前最新章号 → high pacing。
      2. 高优先级长期挂账：priority>=4 + status=open + 跨度 > 100 章 → medium。
      3. 主线被弃：priority>=5 + status=dropped → high continuity。
    """
    if not foreshadows:
        return []
    sorted_chapters = sorted(
        [c.get("number") for c in chapters if isinstance(c.get("number"), int)]
    )
    if not sorted_chapters:
        return []
    latest_chapter = sorted_chapters[-1]

    issues: list[dict] = []

    for f in foreshadows:
        title = (getattr(f, "title", None) or "未命名伏笔").strip() or "未命名伏笔"
        code = (getattr(f, "code", None) or "").strip()
        label = f"{code}「{title}」" if code else f"「{title}」"
        status = (getattr(f, "status", None) or "open").strip()
        priority = getattr(f, "priority", None) or 3
        laid_no = getattr(f, "laid_chapter_number", None)
        planned_no = getattr(f, "planned_resolve_chapter", None)

        # Rule 3: critical priority dropped
        if status == "dropped" and isinstance(priority, int) and priority >= 5:
            anchor_chapter = laid_no if isinstance(laid_no, int) else latest_chapter
            issues.append({
                "severity": "high",
                "type": "continuity",
                "chapter_numbers": [anchor_chapter],
                "description": (
                    f"高优先级伏笔 {label}（priority={priority}）状态为 dropped，"
                    "属于关键主线悬念被丢弃，会让前期铺垫变成无效投入。"
                    "建议恢复 status=open 并安排在合适卷末回收，或在 character_change 中明确「悬念失效原因」。"
                ),
                "suggested_patch": {
                    "chapter_number": anchor_chapter,
                    "field": "foreshadow",
                    "replacement": "",
                },
            })
            continue

        if status != "open":
            continue

        # Rule 1: planned resolution overdue
        if isinstance(planned_no, int) and planned_no > 0 and planned_no < latest_chapter:
            issues.append({
                "severity": "high",
                "type": "pacing",
                "chapter_numbers": [planned_no],
                "description": (
                    f"伏笔 {label} 计划于第 {planned_no} 章回收，但全书已写到第 {latest_chapter} 章"
                    "仍未结清，属于已过期未回收。"
                    "建议在最近卷末追加回收章节，或显式 dropped 并交代「悬念被新冲突替代」。"
                ),
                "suggested_patch": {
                    "chapter_number": planned_no,
                    "field": "foreshadow",
                    "replacement": "",
                },
            })
            continue

        # Rule 2: high-priority long-aged open
        if (
            isinstance(priority, int)
            and priority >= 4
            and isinstance(laid_no, int)
            and laid_no > 0
            and (latest_chapter - laid_no) > 100
        ):
            issues.append({
                "severity": "medium",
                "type": "pacing",
                "chapter_numbers": [laid_no],
                "description": (
                    f"高优先级伏笔 {label}（priority={priority}）在第 {laid_no} 章埋下，"
                    f"距今已跨越 {latest_chapter - laid_no} 章仍未回收，长期挂账会让读者忘记前文铺垫。"
                    "建议在中段卷末安排显性进展（部分回收/再激活）以维持紧张感。"
                ),
                "suggested_patch": {
                    "chapter_number": laid_no,
                    "field": "foreshadow",
                    "replacement": "",
                },
            })

    return issues


# ─────────────────────────────────────────────────────────────
#  Embedding-based soft duplicate detection
# ─────────────────────────────────────────────────────────────

# 把每章压成一段文本喂给 embedding，再做余弦比较。
# 余弦阈值参考：
#   ≥ 0.92 → 几乎确定重复（critical）
#   ≥ 0.85 → 高度相似软重复（high）
#   ≥ 0.78 → 怀疑同质化（medium）
SEMANTIC_DUP_THRESHOLD_HIGH = 0.85
SEMANTIC_DUP_THRESHOLD_MEDIUM = 0.78
SEMANTIC_DUP_WINDOW_VOLUME = 9999      # volume 范围内全配对
SEMANTIC_DUP_WINDOW_BOOK = 60          # book 范围内只比相邻 60 章


def _outline_chapter_signature_text(chapter: dict) -> str:
    parts: list[str] = []
    for field in ("title", "core_event", "character_change", "end_hook"):
        text = _clean_outline_text(chapter.get(field), 220)
        if text:
            parts.append(text)
    return " || ".join(parts)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a ** 0.5 * norm_b ** 0.5)


def _detect_outline_embedding_duplicates(
    chapters: list[dict],
    vectors_by_number: dict[int, list[float]],
    *,
    scope: str = "volume",
    threshold_high: float = SEMANTIC_DUP_THRESHOLD_HIGH,
    threshold_medium: float = SEMANTIC_DUP_THRESHOLD_MEDIUM,
) -> list[dict]:
    """
    纯函数：对已经向量化好的章节做两两余弦比较，超过阈值视为软重复。
      - cosine ≥ threshold_high → high 严重度（追读节奏受损）。
      - cosine ≥ threshold_medium → medium 严重度（提示同质化）。
    跨距过远的对（在 book 范围下 > SEMANTIC_DUP_WINDOW_BOOK）不参与比较。
    """
    if not chapters or len(vectors_by_number) < 2:
        return []
    sorted_chapters = sorted(
        [c for c in chapters if isinstance(c.get("number"), int) and c["number"] in vectors_by_number],
        key=lambda c: c["number"],
    )
    if len(sorted_chapters) < 2:
        return []

    window = SEMANTIC_DUP_WINDOW_VOLUME if scope == "volume" else SEMANTIC_DUP_WINDOW_BOOK

    issues: list[dict] = []
    seen_pairs: set[tuple[int, int]] = set()

    for i, ch_a in enumerate(sorted_chapters):
        n_a = ch_a["number"]
        v_a = vectors_by_number[n_a]
        for ch_b in sorted_chapters[i + 1:]:
            n_b = ch_b["number"]
            if n_b - n_a > window:
                break
            pair = (n_a, n_b)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            v_b = vectors_by_number[n_b]
            sim = _cosine_similarity(v_a, v_b)
            if sim >= threshold_high:
                severity = "high"
            elif sim >= threshold_medium:
                severity = "medium"
            else:
                continue
            label_a = _clean_outline_text(ch_a.get("title"), 32) or f"第{n_a}章"
            label_b = _clean_outline_text(ch_b.get("title"), 32) or f"第{n_b}章"
            issues.append({
                "severity": severity,
                "type": "duplicate_event",
                "chapter_numbers": [n_a, n_b],
                "description": (
                    f"第{n_a}章《{label_a}》与第{n_b}章《{label_b}》语义相似度 {sim:.2f}，"
                    "两章在核心事件、人物变化和章末钩子上高度同质，会让读者产生"
                    "「重复看了一遍」的疲劳感。建议拆解为「阶段性失败 → 卷末高潮」"
                    "的递进结构，避免同一目标被反复完成。"
                ),
                "suggested_patch": {
                    "chapter_number": n_b,
                    "field": "core_event",
                    "replacement": "",
                },
            })

    return issues


async def compute_outline_chapter_vectors(
    chapters: list[dict],
) -> dict[int, list[float]]:
    """
    异步：对每个章节签名文本调 embedding_service.embed_texts 拿向量。
    任何失败都安全降级返回空 dict（不影响 QC 主流程）。
    """
    from app.services.embedding_service import embed_texts

    pairs: list[tuple[int, str]] = []
    for chapter in chapters:
        number = chapter.get("number")
        if not isinstance(number, int):
            continue
        text = _outline_chapter_signature_text(chapter)
        if not text:
            continue
        pairs.append((number, text))
    if len(pairs) < 2:
        return {}
    try:
        vectors = await embed_texts([text for _, text in pairs])
    except Exception:
        return {}
    if not vectors or len(vectors) != len(pairs):
        return {}
    return {number: vec for (number, _), vec in zip(pairs, vectors) if isinstance(vec, list)}


async def analyze_outline_embedding_duplicates(
    chapters: list[dict],
    *,
    scope: str = "volume",
) -> dict:
    """
    异步包装：取向量 → 比对 → 返回与 _detect_outline_hard_rule_issues 同结构的报告。
    embedding 不可用或失败时返回 pass 报告，不阻塞 QC。
    """
    vectors = await compute_outline_chapter_vectors(chapters)
    if not vectors:
        return {
            "overall_score": 100,
            "status": "pass",
            "summary": "embedding 语义去重未运行（向量服务不可用或样本不足）。",
            "issues": [],
            "must_fix_chapter_numbers": [],
        }
    issues = _detect_outline_embedding_duplicates(chapters, vectors, scope=scope)
    if not issues:
        return {
            "overall_score": 100,
            "status": "pass",
            "summary": "embedding 语义去重未发现软重复。",
            "issues": [],
            "must_fix_chapter_numbers": [],
        }
    must_fix = sorted({
        n for issue in issues for n in issue.get("chapter_numbers", []) if isinstance(n, int)
    })
    score = min(_HARD_RULE_SEVERITY_TO_SCORE.get(i.get("severity", ""), 80) for i in issues)
    return {
        "overall_score": score,
        "status": "fail",
        "summary": f"embedding 语义去重发现 {len(issues)} 对软重复章节。",
        "issues": issues,
        "must_fix_chapter_numbers": must_fix,
    }


_HARD_RULE_SEVERITY_TO_SCORE: dict[str, int] = {
    "critical": 55,
    "high": 70,
    "medium": 80,
    "low": 90,
}


def _detect_outline_hard_rule_issues(
    chapters: list[dict],
    *,
    power_systems=None,
    genre: str = "",
    scope: str = "volume",
    characters=None,
    theme_statement: str = "",
    premise: str = "",
    foreshadows=None,
) -> dict:
    """
    Deterministic outline checks for failures that should not depend on LLM judgment.
    Sub-checks:
      1. Exact mirrored chapter endings (duplicate_event / critical) — always on.
      2. Power-system terminology drift (continuity / critical) — when power_systems provided.
      3. Realm regression without trigger + end-of-book pacing collapse
         (continuity / pacing / high) — when power_systems provided.
      4. Character death without revival mechanism (continuity / critical)
         — when characters provided.
      5. Theme alignment (theme_alignment / medium) — when theme_statement contains
         self-determination keywords (我命由我 / 凡人逆袭 / 草根崛起 ...).
      6. Foreshadow ledger overdue / abandoned (pacing or continuity / medium-high)
         — when foreshadows provided.

    Backward compatibility: when all extra context kwargs are absent, only the
    duplicate_event check runs and the original score (55 on fail, 100 on pass) is
    preserved.
    """
    issues: list[dict] = []
    must_fix: set[int] = set()
    protagonist_names = _collect_protagonist_anchor_names(characters)

    # Sub-check 1: exact mirrored core_event/character_change/end_hook (existing logic)
    signatures: dict[tuple[str, str, str], list[int]] = {}
    for chapter in chapters:
        signature = _chapter_duplicate_signature(chapter)
        number = chapter.get("number")
        if signature is None or not isinstance(number, int):
            continue
        signatures = {
            **signatures,
            signature: [*signatures.get(signature, []), number],
        }
    for numbers in signatures.values():
        if len(numbers) < 2:
            continue
        ordered_numbers = sorted(numbers)
        must_fix = {*must_fix, *ordered_numbers}
        issues.append({
            "severity": "critical",
            "type": "duplicate_event",
            "chapter_numbers": ordered_numbers,
            "description": (
                f"第{'、'.join(str(n) for n in ordered_numbers)}章的核心事件、人物变化、章末钩子完全一致，"
                "属于确定性镜像重复，会制造多个同质结局或循环节点。"
            ),
            "suggested_patch": {
                "chapter_number": ordered_numbers[-1],
                "field": "core_event",
                "replacement": "",
            },
        })

    # Sub-check 2: terminology hard whitelist/blacklist
    terminology_issues = _detect_outline_terminology_issues(
        chapters,
        power_systems=power_systems,
        genre=genre,
    )
    for issue in terminology_issues:
        for number in issue.get("chapter_numbers", []) or []:
            if isinstance(number, int):
                must_fix.add(number)
    issues.extend(terminology_issues)

    # Sub-check 3: realm regression + end-of-book pacing
    power_curve_issues = _detect_outline_power_curve_issues(
        chapters,
        power_systems=power_systems,
        scope=scope,
        protagonist_names=protagonist_names or None,
    )
    for issue in power_curve_issues:
        for number in issue.get("chapter_numbers", []) or []:
            if isinstance(number, int):
                must_fix.add(number)
    issues.extend(power_curve_issues)

    # Sub-check 4: character death continuity
    death_issues = _detect_outline_character_death_continuity(
        chapters,
        characters=characters,
    )
    for issue in death_issues:
        for number in issue.get("chapter_numbers", []) or []:
            if isinstance(number, int):
                must_fix.add(number)
    issues.extend(death_issues)

    # Sub-check 5: theme alignment
    theme_protagonist_names = [
        getattr(char, "name", None) for char in (characters or [])
        if getattr(char, "role", None) == "protagonist" and getattr(char, "name", None)
    ]
    theme_issues = _detect_outline_theme_alignment_issues(
        chapters,
        theme_statement=theme_statement,
        premise=premise,
        protagonist_names=theme_protagonist_names,
    )
    for issue in theme_issues:
        for number in issue.get("chapter_numbers", []) or []:
            if isinstance(number, int):
                must_fix.add(number)
    issues.extend(theme_issues)

    # Sub-check 6: foreshadow ledger
    foreshadow_issues = _detect_outline_foreshadow_issues(
        chapters,
        foreshadows=foreshadows,
    )
    for issue in foreshadow_issues:
        for number in issue.get("chapter_numbers", []) or []:
            if isinstance(number, int):
                must_fix.add(number)
    issues.extend(foreshadow_issues)

    if not issues:
        return {
            "overall_score": 100,
            "status": "pass",
            "summary": "硬规则未发现确定性结构问题。",
            "issues": [],
            "must_fix_chapter_numbers": [],
        }

    score = min(
        _HARD_RULE_SEVERITY_TO_SCORE.get(issue.get("severity", ""), 80)
        for issue in issues
    )

    return {
        "overall_score": score,
        "status": "fail",
        "summary": f"硬规则发现 {len(issues)} 个确定性结构问题。",
        "issues": issues,
        "must_fix_chapter_numbers": sorted(must_fix),
    }


def _merge_outline_quality_reports(ai_report: dict, hard_report: dict) -> dict:
    hard_issues = hard_report.get("issues") if isinstance(hard_report, dict) else []
    if not hard_issues:
        return ai_report

    ai_issues = ai_report.get("issues") if isinstance(ai_report, dict) else []
    ai_must_fix = ai_report.get("must_fix_chapter_numbers") if isinstance(ai_report, dict) else []
    hard_must_fix = hard_report.get("must_fix_chapter_numbers") or []
    merged_must_fix = sorted({
        *[n for n in ai_must_fix if isinstance(n, int)],
        *[n for n in hard_must_fix if isinstance(n, int)],
    })

    ai_score = ai_report.get("overall_score") if isinstance(ai_report, dict) else None
    hard_score = hard_report.get("overall_score", 55)
    score = min(ai_score if isinstance(ai_score, int) else 100, hard_score)
    ai_summary = ai_report.get("summary", "") if isinstance(ai_report, dict) else ""
    hard_summary = hard_report.get("summary", "")
    summary = "；".join(part for part in [hard_summary, ai_summary] if part)

    return {
        **(ai_report if isinstance(ai_report, dict) else {}),
        "overall_score": score,
        "status": "fail",
        "summary": summary,
        "issues": [*hard_issues, *(ai_issues if isinstance(ai_issues, list) else [])],
        "must_fix_chapter_numbers": merged_must_fix,
    }


def _format_outline_quality_label(node_title: str, report: dict, scope: str) -> str:
    scope_name = "全书" if scope == "book" else "卷内"
    if not isinstance(report, dict) or report.get("error"):
        return f"《{node_title}》{scope_name}质检失败：{report.get('error', '未知错误') if isinstance(report, dict) else '未知错误'}"
    score = report.get("overall_score", "-")
    status = report.get("status", "-")
    must_fix = report.get("must_fix_chapter_numbers") or []
    suffix = f"，必修章节：{'、'.join(str(num) for num in must_fix)}" if must_fix else ""
    return f"《{node_title}》{scope_name}质检完成：{score}分 / {status}{suffix}"


def _sse_outline_quality_progress(
    *,
    step: int,
    total_steps: int,
    label: str,
    scope: str,
    progress_key_suffix: str,
    report: dict | None = None,
    done: bool = True,
    error: bool = False,
) -> str:
    """SSE 进度行：携带结构化大纲质检结果供前端展开；progress_key 避免与同日 step 的其他进度行合并。"""
    payload: dict = {
        "event": "progress",
        "step": step,
        "total": total_steps,
        "label": label,
        "done": done,
        "error": error,
        "progress_key": f"{step}-outline-quality-{scope}-{progress_key_suffix}",
        "outline_quality_scope": scope,
    }
    if report is not None:
        payload["outline_quality_report"] = report
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _outline_node_to_chapter_context(node: OutlineNode) -> dict:
    title_text = str(node.title or "")
    match = re.match(r"第(\d+)章[:：]\s*(.*)", title_text)
    number = display_chapter_number(title_text, getattr(node, "sort_order", None))
    title = match.group(2).strip() if match else title_text
    extra = node.extra if isinstance(node.extra, dict) else {}
    return {
        "number": number,
        "title": title or "未命名",
        "core_event": node.summary or "",
        "opening_hook": node.hook or "",
        "character_change": node.conflict or "",
        "foreshadow": extra.get("foreshadow", ""),
        "end_hook": extra.get("end_hook") or node.highlight or "",
        "pacing": extra.get("pacing", "medium"),
        "word_estimate": extra.get("word_estimate", TARGET_WORDS_PER_CHAPTER),
    }


def _anchor_volume_for_expand(node: OutlineNode, id_map: dict) -> OutlineNode | None:
    """从当前展开节点向上找到所属卷（用于判断「前几卷」范围）。"""
    cur: OutlineNode | None = node
    seen: set = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        if getattr(cur, "node_type", None) == "volume":
            return cur
        pid = cur.parent_id
        if not pid:
            return None
        cur = id_map.get(pid)
    return None


def _chapter_plan_root_volume(node: OutlineNode, id_map: dict) -> OutlineNode | None:
    """章节计划所属根卷（parent 链上第一个 volume）。"""
    cur: OutlineNode | None = node
    seen: set = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        if getattr(cur, "node_type", None) == "volume":
            return cur
        if not cur.parent_id:
            return None
        cur = id_map.get(cur.parent_id)
    return None


def _prior_volume_chapter_plan_nodes(
    all_nodes: list[OutlineNode],
    id_map: dict,
    anchor_volume: OutlineNode,
) -> list[OutlineNode]:
    """严格早于 anchor 卷的根卷下，所有已落库的 chapter_plan。"""
    anchor_order = anchor_volume.sort_order or 0
    out: list[OutlineNode] = []
    for n in all_nodes:
        if getattr(n, "node_type", None) != "chapter_plan":
            continue
        root = _chapter_plan_root_volume(n, id_map)
        if root is None or getattr(root, "node_type", None) != "volume":
            continue
        if (root.sort_order or 0) < anchor_order:
            out.append(n)
    return out


def _sort_chapter_plan_nodes(nodes: list[OutlineNode]) -> list[OutlineNode]:
    def sort_key(n: OutlineNode):
        ctx = _outline_node_to_chapter_context(n)
        num = ctx.get("number")
        try:
            inum = int(num) if num is not None else 0
        except (TypeError, ValueError):
            inum = 0
        return (inum, str(n.id))

    return sorted(nodes, key=sort_key)


def _compact_prior_volume_plot_lines(
    chapters_ctx: list[dict],
    *,
    core_lim: int,
    hook_lim: int,
    fs_lim: int,
) -> list[str]:
    lines: list[str] = []
    for ch in chapters_ctx:
        num = ch.get("number") if ch.get("number") is not None else "?"
        title = _clean_outline_text(ch.get("title"), 48)
        core = _clean_outline_text(ch.get("core_event"), core_lim)
        hook = _clean_outline_text(ch.get("end_hook"), hook_lim)
        fs = _clean_outline_text(ch.get("foreshadow"), fs_lim)
        line = f"第{num}章《{title}》| 核心：{core} | 章末：{hook}"
        if fs:
            line += f" | 伏笔：{fs}"
        lines.append(line)
    return lines


def _format_prior_volumes_plot_context(chapters_ctx: list[dict], max_chars: int) -> str:
    """前几卷章纲情节链：优先保留全部章节，通过缩短字段适配 token；仍过长则截断并提示。"""
    if not chapters_ctx or max_chars < 120:
        return ""
    for core_lim, hook_lim, fs_lim in ((90, 72, 72), (60, 48, 48), (42, 36, 36), (28, 24, 24)):
        lines = _compact_prior_volume_plot_lines(
            chapters_ctx, core_lim=core_lim, hook_lim=hook_lim, fs_lim=fs_lim
        )
        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text
    return text[: max_chars - 24] + "\n…（前几卷情节链过长已截断）"


def _build_prior_foreshadow_ledger(
    chapters_ctx: list[dict],
    foreshadow_rows: list[Foreshadow],
    max_chars: int,
) -> str:
    """章纲五要素中的伏笔行 + 伏笔表中仍未回收的条目。"""
    if max_chars < 80:
        return ""
    parts: list[str] = []
    used: set[str] = set()
    ch_lines: list[str] = []
    for ch in chapters_ctx:
        raw = (ch.get("foreshadow") or "").strip()
        if not raw:
            continue
        key = raw[:240]
        if key in used:
            continue
        used.add(key)
        num = ch.get("number") if ch.get("number") is not None else "?"
        ch_lines.append(f"第{num}章：{raw}")
    if ch_lines:
        parts.append("【来自前几卷章纲五要素】\n" + "\n".join(ch_lines))

    db_lines: list[str] = []
    open_rows = [f for f in foreshadow_rows if (f.status or "open") == "open"]
    open_rows.sort(key=lambda f: (-(f.priority or 3), str(f.id)))
    for f in open_rows:
        code = f.code or "—"
        title = _clean_outline_text(f.title, 80)
        desc = _clean_outline_text(f.description, 140)
        plan = f.planned_resolve_chapter
        plan_s = f"预计第{plan}章回收" if plan else "回收章未定"
        db_lines.append(f"{code} {title} | {plan_s} | {desc}")
    if db_lines:
        parts.append("【伏笔表（仍未回收）】\n" + "\n".join(db_lines))

    text = "\n\n".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…（伏笔台账过长已截断）"
    return text


def _build_overdue_foreshadow_ledger(
    foreshadow_rows: list,
    max_chapter_number: int,
    max_chars: int = 2000,
) -> str:
    """
    从伏笔表中筛选「已逾期未回收」条目并格式化为字符串。
    逾期定义：status=open AND planned_resolve_chapter <= max_chapter_number
    """
    if not foreshadow_rows or max_chapter_number <= 0:
        return ""
    overdue = [
        f for f in foreshadow_rows
        if (f.status or "open") == "open"
        and f.planned_resolve_chapter
        and f.planned_resolve_chapter <= max_chapter_number
    ]
    if not overdue:
        return ""
    overdue.sort(key=lambda f: (-(f.priority or 3), f.planned_resolve_chapter or 0))
    lines: list[str] = []
    for f in overdue:
        code = f.code or "—"
        title = _clean_outline_text(f.title, 60)
        plan = f.planned_resolve_chapter
        desc = _clean_outline_text(f.description, 100)
        lines.append(f"{code} {title} | 应于第{plan}章前回收（已逾期） | {desc}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…（逾期列表过长已截断）"
    return text


def _ai_expand_prior_plot_budget(model_profile: str) -> int:
    return 14000 if model_profile == "gemini" else 6500


def _ai_expand_prior_foreshadow_budget(model_profile: str) -> int:
    return 8000 if model_profile == "gemini" else 3200


def _load_existing_chapter_context(
    db: Session,
    project_id: str,
    limit: int = 24,
) -> list[dict]:
    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
    ).all()
    chapters = [_outline_node_to_chapter_context(node) for node in nodes]
    chapters.sort(key=lambda chapter: chapter.get("number") or 0)
    return chapters[-limit:]


def _outline_snapshot_payload(nodes: list[OutlineNode]) -> dict:
    ordered = sorted(
        nodes,
        key=lambda node: (
            0 if node.parent_id is None else 1,
            node.sort_order or 0,
            str(node.id),
        ),
    )
    return {
        "schema_version": 1,
        "nodes": [
            {
                "id": str(node.id),
                "parent_id": str(node.parent_id) if node.parent_id else None,
                "node_type": node.node_type,
                "title": node.title,
                "summary": node.summary,
                "hook": node.hook,
                "highlight": node.highlight,
                "conflict": node.conflict,
                "sort_order": node.sort_order,
                "expected_words": node.expected_words,
                "reader_hook_score": node.reader_hook_score,
                "storyline_ids": node.storyline_ids or [],
                "involved_character_ids": node.involved_character_ids or [],
                "key_item_ids": node.key_item_ids or [],
                "key_skill_ids": node.key_skill_ids or [],
                "emotional_tone": node.emotional_tone,
                "pacing": node.pacing,
                "power_milestone": node.power_milestone,
                "foreshadows_laid": node.foreshadows_laid or [],
                "foreshadows_resolved": node.foreshadows_resolved or [],
                "extra": node.extra if isinstance(node.extra, dict) else {},
            }
            for node in ordered
        ],
    }


def _create_outline_revision(
    db: Session,
    *,
    project_id: str,
    label: str,
    source: str,
    scope: str = "book",
    volume_node_id: UUID | None = None,
    note: str | None = None,
    meta: dict[str, Any] | None = None,
) -> OutlineRevision:
    q = db.query(OutlineNode).filter(OutlineNode.project_id == project_id)
    if scope == "volume" and volume_node_id:
        direct_children = db.query(OutlineNode.id).filter(
            OutlineNode.project_id == project_id,
            OutlineNode.parent_id == volume_node_id,
        ).all()
        child_ids = [row[0] for row in direct_children]
        q = q.filter(
            (OutlineNode.id == volume_node_id)
            | (OutlineNode.parent_id == volume_node_id)
            | (OutlineNode.parent_id.in_(child_ids))
        )
    nodes = q.order_by(OutlineNode.sort_order, OutlineNode.created_at).all()
    snapshot = _outline_snapshot_payload(nodes)
    revision = OutlineRevision(
        project_id=project_id,
        label=label,
        source=source,
        scope=scope,
        volume_node_id=volume_node_id,
        note=note,
        snapshot=snapshot,
        meta=meta or {},
        node_count=len(snapshot["nodes"]),
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision


def _load_volume_chapter_context(
    db: Session,
    project_id: str,
    volume_node: OutlineNode,
) -> list[dict]:
    """
    Load chapter plans under a volume, including the legacy volume -> arc -> chapter_plan shape.
    """
    children = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.parent_id == volume_node.id,
    ).all()
    parent_ids = [volume_node.id, *[child.id for child in children if child.node_type == "arc"]]
    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
        OutlineNode.parent_id.in_(parent_ids),
    ).all()
    chapters = [_outline_node_to_chapter_context(node) for node in nodes]
    chapters.sort(key=lambda chapter: chapter.get("number") or 0)
    return chapters


def _chapter_number_value(chapter: dict) -> int:
    number = chapter.get("number")
    return number if isinstance(number, int) else 0


def _with_outline_quality(report_owner: OutlineNode, report: dict) -> dict:
    current_extra = report_owner.extra if isinstance(report_owner.extra, dict) else {}
    return {
        **current_extra,
        "outline_quality": report,
    }


def _create_quality_revision(
    db: Session,
    *,
    project_id: str,
    scope: str,
    report: dict[str, Any],
    volume_node: OutlineNode | None = None,
) -> OutlineRevision:
    if scope == "volume" and volume_node is not None:
        label = f"质检报告：{volume_node.title}"
        note = "单卷大纲质检自动留档"
        volume_node_id = volume_node.id
    else:
        label = "质检报告：全书大纲"
        note = "全书大纲质检自动留档"
        volume_node_id = None
    return _create_outline_revision(
        db,
        project_id=project_id,
        label=label,
        source="quality",
        scope="volume" if scope == "volume" else "book",
        volume_node_id=volume_node_id,
        note=note,
        meta={
            "quality_scope": scope,
            "quality_status": report.get("status"),
            "quality_score": report.get("overall_score"),
            "quality_report": report,
        },
    )


def _outline_node_plan_fields(node: OutlineNode) -> dict:
    extra = node.extra if isinstance(node.extra, dict) else {}
    return {
        "opening_hook": node.hook or "",
        "core_event": node.summary or "",
        "character_change": node.conflict or "",
        "foreshadow": extra.get("foreshadow", ""),
        "end_hook": extra.get("end_hook") or node.highlight or "",
    }


def _apply_outline_patch_to_node(node: OutlineNode, patch: dict) -> dict:
    before = _outline_node_plan_fields(node)
    fields = patch.get("fields") if isinstance(patch.get("fields"), dict) else patch
    extra = node.extra if isinstance(node.extra, dict) else {}
    next_extra = {**extra}

    opening_hook = fields.get("opening_hook")
    core_event = fields.get("core_event")
    character_change = fields.get("character_change")
    foreshadow = fields.get("foreshadow")
    end_hook = fields.get("end_hook")

    if isinstance(opening_hook, str) and opening_hook.strip():
        node.hook = opening_hook.strip()
    if isinstance(core_event, str) and core_event.strip():
        node.summary = core_event.strip()
    if isinstance(character_change, str) and character_change.strip():
        node.conflict = character_change.strip()
    if isinstance(foreshadow, str):
        next_extra["foreshadow"] = foreshadow.strip()
    if isinstance(end_hook, str) and end_hook.strip():
        node.highlight = end_hook.strip()
        next_extra["end_hook"] = end_hook.strip()

    node.extra = next_extra
    after = _outline_node_plan_fields(node)
    return {
        "chapter_number": patch.get("chapter_number"),
        "node_id": str(node.id) if node.id else None,
        "title": node.title,
        "before": before,
        "after": after,
        "reason": patch.get("reason", ""),
    }


