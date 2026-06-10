"""dabai 章末总结提取：分类 JSON → 图事实 + 向量记忆。"""
from __future__ import annotations

from typing import Any

_DEBRIEF_SYSTEM = (
    "你是网文编辑，负责从章节正文提取结构化事实。"
    "只返回 JSON，分 graph_facts（关系/境界/移动）与 vector_memories（事件语义）。"
)


def build_debrief_prompt(
    *,
    chapter_title: str,
    chapter_number: int,
    content: str,
    plan_summary: str,
) -> tuple[str, str]:
    user = (
        f"第{chapter_number}章 {chapter_title}\n"
        f"章纲摘要：{plan_summary[:400]}\n\n"
        f"正文（节选）：{(content or '')[:6000]}\n\n"
        "返回 JSON：\n"
        "{\n"
        '  "graph_facts": [\n'
        '    {"type": "at_realm", "character": "主角名", "realm_rank": 2, "chapter": N},\n'
        '    {"type": "traveled", "character": "主角名", "from": "A", "to": "B", "reason": "...", "chapter": N},\n'
        '    {"type": "relation", "a": "主角", "b": "反派", "edge": "HOSTILE", "reason": "...", "chapter": N}\n'
        "  ],\n"
        '  "vector_memories": [\n'
        '    {"memory_type": "event", "title": "短标题", "content": "1-3句", '
        '"tags": ["打脸"], "importance": 0.8}\n'
        "  ],\n"
        '  "warnings": ["与设定可能不一致的点"]\n'
        "}"
    )
    return _DEBRIEF_SYSTEM, user


async def extract_dabai_debrief(svc: Any, *, chapter_number: int, title: str,
                              content: str, plan_summary: str) -> dict:
    from app.services.bootstrap.parse import parse_json

    system, user = build_debrief_prompt(
        chapter_title=title,
        chapter_number=chapter_number,
        content=content,
        plan_summary=plan_summary,
    )
    raw = await svc._call_with_retry(
        system, user, task="dabai.debrief", max_tokens=2048,
    )
    data = parse_json(raw)
    if not isinstance(data, dict):
        data = {}
    return {
        "graph_facts": data.get("graph_facts") or [],
        "vector_memories": data.get("vector_memories") or [],
        "warnings": data.get("warnings") or [],
    }
