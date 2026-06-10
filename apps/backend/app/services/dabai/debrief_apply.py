"""dabai 章末总结落库：Neo4j + MemoryChunk。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Chapter, MemoryChunk, OutlineNode, Project
from app.services.dabai.debrief_extract import extract_dabai_debrief
from app.services.dabai.neo4j_sync import apply_graph_facts
from app.services.embedding_service import embed_chunk_async

logger = logging.getLogger(__name__)


def _plan_for_chapter(db: Session, project_id: str, chapter: Chapter) -> OutlineNode | None:
    return (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "chapter_plan",
            OutlineNode.sort_order == (chapter.chapter_number or 1) - 1,
        )
        .first()
    )


async def _apply_async(
    db: Session,
    project: Project,
    chapter: Chapter,
    svc: Any,
) -> dict:
    plan = _plan_for_chapter(db, str(project.id), chapter)
    dabai = (plan.extra or {}).get("dabai") if plan else {}
    plan_summary = (
        f"{dabai.get('shuang_type', '')} {dabai.get('shuang_payoff', '')}"
        if dabai else (plan.summary if plan else "")
    )
    extracted = await extract_dabai_debrief(
        svc,
        chapter_number=chapter.chapter_number or 1,
        title=chapter.title or "",
        content=chapter.content or "",
        plan_summary=plan_summary or "",
    )
    graph_status = apply_graph_facts(str(project.id), extracted.get("graph_facts") or [])

    new_chunks: list[MemoryChunk] = []
    for mem in extracted.get("vector_memories") or []:
        if not isinstance(mem, dict) or not mem.get("content"):
            continue
        chunk = MemoryChunk(
            project_id=project.id,
            chapter_id=chapter.id,
            memory_type=mem.get("memory_type") or "event",
            title=(mem.get("title") or "")[:200],
            content=mem["content"],
            chapter_number=chapter.chapter_number,
            tags=mem.get("tags") or [],
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
        "vector_count": len(new_chunks),
        "warnings": extracted.get("warnings") or [],
    }


def apply_dabai_debrief_sync(
    db: Session,
    project: Project,
    chapter: Chapter,
    svc: Any,
) -> dict:
    """同步包装（供 chapter_debrief 路由调用）。"""
    try:
        return asyncio.run(_apply_async(db, project, chapter, svc))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_apply_async(db, project, chapter, svc))
        finally:
            loop.close()
