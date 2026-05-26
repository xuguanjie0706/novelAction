"""
context_builder_chat.py — Chat 模式上下文构建

职责：为大纲 Chat 和写作 Chat 构建结构化上下文字符串。
  format_outline_chat_context                → 大纲讨论上下文
  format_writing_chat_context                → 写作讨论上下文
  append_reference_chapters_to_writing_context → 附加参考章节
"""

from __future__ import annotations

import json
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Chapter, Character, OutlineNode, PowerSystem, Project, StoryLine
from app.routers.ai.text_utils import plain_text, truncate
from app.services.ai.context_builder_continuity import fmt_index_item
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block
from app.utils.chapter_numbering import display_chapter_number


def format_outline_chat_foreshadows(node: OutlineNode) -> str:
    """将大纲节点的伏笔字段格式化为简短描述串。"""
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
    """将单个大纲节点格式化为单行/多行描述。"""
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
    """构建大纲 Chat 完整上下文（作品信息 + 人物 + 力量体系 + 故事线 + 大纲树）。"""
    sections = ["【作品】", f"标题：{project.title}"]
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
    """构建写作 Chat 上下文（作品摘要 + 当前章 + 上一章结尾 + 当前正文）。"""
    sections = ["【作品】", f"标题：{project.title}"]
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
    """
    将作者指定的参考章节追加到写作上下文末尾。

    多章参考时按章均分总预算（28000 or 36000 chars），降低模型流式断连概率。
    """
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
    ref_count = len(ordered)
    ref_total_budget = 28000 if ref_count > 3 else 36000
    per_chapter_cap = max(1800, min(12000, ref_total_budget // ref_count))
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
        body = (narr.strip() if narr.strip() else pl)[:per_chapter_cap]
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
