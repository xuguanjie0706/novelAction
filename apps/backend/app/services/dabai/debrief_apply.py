"""dabai 章末总结落库：Neo4j 图事实 + MemoryChunk 向量记忆。

⚠️ 历史 bug 备忘（2026-06 修复）：
  - 旧版调用 ``chapter.chapter_number``，但 Chapter 模型没有该字段 → AttributeError，
    被路由层 try/except 吞掉 → 图谱/向量记忆从未写入过（写章衔接差的根因之一）。
    现统一用 ``chapter_display_number(chapter)``（sort_order+1）。
  - 旧版自带 ``_plan_for_chapter`` 用 sort_order==chapter_number-1 错位匹配，
    现复用 ``resolve_chapter_plan``（outline_node_id 优先）。
  - 重复复盘会重复写 MemoryChunk，现按 tag=dabai_debrief 先删后写（幂等）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Chapter, Character, MemoryChunk, Project
from app.services.dabai.debrief_extract import extract_dabai_debrief
from app.services.dabai.neo4j_sync import apply_graph_facts
from app.services.dabai.outline_plan import chapter_display_number, resolve_chapter_plan
from app.services.embedding_service import embed_chunk_async

logger = logging.getLogger(__name__)

DABAI_DEBRIEF_TAG = "dabai_debrief"  # 幂等标记：重跑复盘先删同 tag 旧记忆


def _known_character_names(db: Session, project: Project, limit: int = 12) -> list[str]:
    """标准人名清单：注入提取 prompt，强制图事实使用与人物档案一致的名字。"""
    rows = (
        db.query(Character.name, Character.role)
        .filter(Character.project_id == project.id)
        .order_by(Character.created_at.asc())
        .limit(limit * 2)
        .all()
    )
    # 主角排最前，便于 prompt 指认
    names = [r[0] for r in rows if r[1] == "protagonist"] + [
        r[0] for r in rows if r[1] != "protagonist"
    ]
    return [n for n in names if n][:limit]


def _delete_stale_chunks(db: Session, chapter: Chapter) -> int:
    """删除本章上一轮 dabai 复盘写入的记忆（按 tag 过滤，避免误删主链路记忆）。"""
    rows = (
        db.query(MemoryChunk)
        .filter(MemoryChunk.chapter_id == chapter.id)
        .all()
    )
    deleted = 0
    for row in rows:
        if DABAI_DEBRIEF_TAG in (row.tags or []):
            db.delete(row)
            deleted += 1
    if deleted:
        db.flush()
    return deleted


async def apply_dabai_debrief(
    db: Session,
    project: Project,
    chapter: Chapter,
    svc: Any,
) -> dict:
    """异步复盘入口：提取 → Neo4j 图事实 + MemoryChunk（幂等）→ 返回摘要。

    调用方负责 db.commit()。
    Returns:
        {graph_sync, graph_fact_count, vector_count, stale_deleted, warnings,
         memories: [{title, memory_type, importance}]}
    """
    ch_no = chapter_display_number(chapter)
    plan = resolve_chapter_plan(db, str(project.id), chapter)
    dabai = (plan.extra or {}).get("dabai") if plan else {}
    plan_summary = (
        f"{dabai.get('shuang_type', '')} {dabai.get('shuang_payoff', '')}"
        if dabai else (plan.summary if plan else "")
    )
    known_names = _known_character_names(db, project)
    extracted = await extract_dabai_debrief(
        svc,
        chapter_number=ch_no,
        title=chapter.title or "",
        content=chapter.content or "",
        plan_summary=plan_summary or "",
        known_characters=known_names,
    )

    # 图事实：补齐缺失的 chapter 字段后落 Neo4j
    facts = []
    for fact in extracted.get("graph_facts") or []:
        if isinstance(fact, dict):
            fact.setdefault("chapter", ch_no)
            facts.append(fact)
    graph_status = apply_graph_facts(str(project.id), facts)

    # 向量记忆：幂等（先删同章旧 dabai 记忆，再写新）
    stale = _delete_stale_chunks(db, chapter)
    new_chunks: list[MemoryChunk] = []
    for mem in extracted.get("vector_memories") or []:
        if not isinstance(mem, dict) or not mem.get("content"):
            continue
        tags = [str(t) for t in (mem.get("tags") or []) if t]
        if DABAI_DEBRIEF_TAG not in tags:
            tags.append(DABAI_DEBRIEF_TAG)
        chunk = MemoryChunk(
            project_id=project.id,
            chapter_id=chapter.id,
            memory_type=mem.get("memory_type") or "event",
            title=(mem.get("title") or "")[:200],
            content=mem["content"],
            chapter_number=ch_no,
            tags=tags,
            importance_score=float(mem.get("importance") or 0.6),
        )
        db.add(chunk)
        new_chunks.append(chunk)
    db.flush()

    from app.database import SessionLocal
    for chunk in new_chunks:
        embed_chunk_async(str(chunk.id), chunk.content, SessionLocal)

    from sqlalchemy.orm.attributes import flag_modified

    extra = dict(project.extra or {})
    extra["graph_sync_status"] = graph_status.get("status")
    project.extra = extra
    flag_modified(project, "extra")

    return {
        "graph_sync": graph_status,
        "graph_fact_count": len(facts),
        "vector_count": len(new_chunks),
        "stale_deleted": stale,
        "warnings": extracted.get("warnings") or [],
        "memories": [
            {
                "title": c.title,
                "memory_type": c.memory_type,
                "importance": c.importance_score,
            }
            for c in new_chunks
        ],
    }


def apply_dabai_debrief_sync(
    db: Session,
    project: Project,
    chapter: Chapter,
    svc: Any,
) -> dict:
    """同步包装（供 chapter_debrief 路由调用）。"""
    try:
        return asyncio.run(apply_dabai_debrief(db, project, chapter, svc))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(apply_dabai_debrief(db, project, chapter, svc))
        finally:
            loop.close()
