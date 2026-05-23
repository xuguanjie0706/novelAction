"""批次上下文、滚动连续性、全书质检说明、字数预算等格式化。"""
from __future__ import annotations

from app.models import OutlineNode
from app.services.outline_planning import TARGET_WORDS_PER_CHAPTER

from app.routers.outline.helpers.text_utils import _clean_outline_text

def _outline_batch_size(_model_profile: str) -> int:
    return 30


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


def _format_rolling_continuity_state(
    chapters: list[dict],
    protagonist_max_rank: int | None = None,
    protagonist_max_realm: str | None = None,
    characters: list | None = None,
) -> str:
    if not chapters:
        return ""

    life_ledger = ""
    if characters is not None:
        from app.routers.outline.helpers.life_state import build_character_life_state_ledger
        life_ledger = build_character_life_state_ledger(chapters, characters)

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

    lines = []
    if life_ledger:
        lines.append(life_ledger)
    lines.extend([
        f"上一批最后章节：第{last_number}章《{last_title}》",
        f"下一批开篇必须承接：{last_hook}",
    ])
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

