"""
context_builder_continuity.py — 连续性上下文构建

职责：跨章事实账本、章节索引导航。
  build_continuity_context   → 人物状态/伏笔/承接点/禁止事项
  build_chapter_index_context → 最近章节索引 + 未回收伏笔导航
  fmt_index_item             → 索引条目格式化工具（供 brief 模块共用）
"""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import (
    Chapter,
    Character,
    ChapterIndex,
    Foreshadow,
    MemoryChunk,
    OutlineNode,
    PowerSystem,
    StoryLine,
)
from app.routers.ai.text_utils import plain_text, truncate
from app.utils.chapter_numbering import display_chapter_number


def fmt_index_item(item) -> str:
    """将索引条目（dict 或其他类型）转为可读字符串。"""
    if isinstance(item, dict):
        return (
            item.get("description")
            or item.get("event")
            or item.get("name")
            or item.get("note")
            or json.dumps(item, ensure_ascii=False)
        )
    return str(item)


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
        # 近期行踪（地点逐章台账末1-2条）：让写章 AI 知道角色"从哪来、为何在此"，
        # 跨章位置跳转若无对应移动记录即为漂移，须在正文交代过程。
        _loc_extra = c.extra if isinstance(c.extra, dict) else {}
        _loc_hist = [h for h in (_loc_extra.get("location_milestones") or []) if isinstance(h, dict)]
        if _loc_hist:
            _tail = _loc_hist[-2:]
            _trail = "；".join(
                f"第{h.get('chapter_number')}章→{h.get('location')}"
                + (f"（{truncate(h.get('reason'), 40)}）" if h.get("reason") else "")
                for h in _tail
            )
            if _trail:
                parts.append(f"近期行踪[{_trail}]")
        if c.current_status and c.current_status != "alive":
            parts.append(f"状态={c.current_status}")
        char_lines.append("、".join(parts))

    power_systems = db.query(PowerSystem).filter(
        PowerSystem.project_id == project_id
    ).order_by(PowerSystem.sort_order).all()
    from app.services.bootstrap.power_registry import build_draft_power_context_from_db
    power_block = build_draft_power_context_from_db(db, project_id)
    power_lines = [power_block] if power_block and power_block != "（未设定境界体系）" else []

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

    _ch_num = chapter.sort_order or 0
    # status="open" 是复盘路径的唯一权威状态；"planned" 仅是章纲规划意图，不在此注入
    global_foreshadows = (
        db.query(Foreshadow)
        .filter(Foreshadow.project_id == project_id, Foreshadow.status == "open")
        .order_by(
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
        is_overdue = bool(
            _ch_num > 0 and f.planned_resolve_chapter and f.planned_resolve_chapter <= _ch_num
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
        "不得无提示跳过上一章钩子的直接反应。",
        "空间连续性：角色本章位置须承接上方「当前位置/近期行踪」；若位置发生变化，必须在正文交代移动过程与原因（耗时、方式、动机），且符合时间线与常理，禁止无交代的瞬移漂移。",
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
        # 「权威台账」标签：此处来源是复盘确认的 status=open 记录，是唯一事实来源
        # 章纲伏笔规划意图（status=planned）在 draft_stream 的「本章伏笔规划意图」区块单独注入
        sections.insert(5, "⚠️未回收伏笔【权威台账，复盘确认，以此为准】（必须可回收或持续铺垫，不得矛盾违背）：\n" +
                         "\n".join(f"  · {l}" for l in foreshadow_lines))
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
