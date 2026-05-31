"""
auto_debrief_route.py — AI 自动复盘分析端点

资源边界：POST /ai/auto-debrief
读取章节正文 → 调用 LLM 提取人物/故事线变化建议 → 缓存到 ChapterDebriefCache。
不写库，仅供前端复盘 Tab 预填并由用户确认后调用 /chapter-debrief 提交。
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Chapter,
    ChapterDebriefCache,
    Character,
    Project,
    ReaderPromise,
    StoryLine,
)
from app.routers.ai.schemas import AutoDebriefRequest
from app.routers.ai.text_utils import chapter_debrief_content_hash, plain_text
from app.services.ai.promise_debrief import enrich_with_promise_ids
from app.services.ai_service import AIService
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block
from app.utils.chapter_numbering import display_chapter_number

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/auto-debrief")
async def auto_debrief(
    project_id: str,
    req: AutoDebriefRequest,
    db: Session = Depends(get_db),
):
    """
    AI 读取章节正文，对照当前人物状态和故事线，
    提取本章发生的状态变化建议。结果仅供前端预填，
    不直接写库——需用户确认后调用 /chapter-debrief 提交。

    请求体 ``cache_only=true`` 时：仅返回与当前正文哈希一致的 ChapterDebriefCache，
    不调用 LLM；无缓存时返回空建议且 ``cache_only_miss=true``。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    if not (chapter.content or "").strip():
        return {
            "character_updates": [],
            "storyline_updates": [],
            "summary": "章节内容为空，无法分析",
        }

    plain_content = plain_text(chapter.content or "")
    narrative_plain, _ = split_plain_manuscript_and_index_block(plain_content)
    if not narrative_plain.strip():
        narrative_plain = plain_content.strip()
    content_hash = chapter_debrief_content_hash(narrative_plain)
    current_llm_provider = str(req.llm_provider_id) if req.llm_provider_id else None

    cached = db.query(ChapterDebriefCache).filter(
        ChapterDebriefCache.project_id == project_id,
        ChapterDebriefCache.chapter_id == chapter.id,
    ).first()
    payload_ok = cached and isinstance(cached.payload, dict)
    hash_ok = payload_ok and cached.content_hash == content_hash

    # 写作页「复盘」Tab 只读预填：正文未改即可复用，不因切换模型线路而丢缓存
    if req.cache_only:
        if hash_ok:
            payload = dict(cached.payload)
            payload["cached"] = True
            return payload
        return {
            "character_updates": [],
            "storyline_updates": [],
            "memory_updates": [],
            "asset_updates": {},
            "new_characters": [],
            "chapter_index": None,
            "summary": "",
            "cached": False,
            "cache_only_miss": True,
        }

    cache_hit = (
        hash_ok
        and not req.force_refresh
        and cached.model_profile == req.model_profile
        and (cached.llm_provider_id or None) == current_llm_provider
    )
    if cache_hit:
        payload = dict(cached.payload)
        payload["cached"] = True
        return payload

    characters = db.query(Character).filter(Character.project_id == project_id).all()
    character_states = [
        {
            "id": str(c.id),
            "name": c.name,
            "current_realm": c.current_realm or "",
            "current_location": c.current_location or "",
            "current_status": c.current_status or "alive",
        }
        for c in characters
    ]

    storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["planned", "active", "climax"]),
    ).all()
    storylines_data = [
        {
            "id": str(s.id),
            "name": s.name,
            "line_type": s.line_type,
            "status": s.status,
            "core_conflict": s.core_conflict or s.description or "",
        }
        for s in storylines
    ]

    open_promise_records = (
        db.query(ReaderPromise)
        .filter(
            ReaderPromise.project_id == project_id,
            ReaderPromise.status == "open",
        )
        .order_by(ReaderPromise.priority.desc())
        .limit(20)
        .all()
    )
    open_promises_data = [
        {
            "id": str(p.id),
            "promise_text": p.promise_text or "",
            "promise_type": p.promise_type or "chapter_ending",
            "source_chapter_number": p.source_chapter_number or "",
            "priority": p.priority or 3,
        }
        for p in open_promise_records
        if (p.promise_text or "").strip()
    ]

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    project = db.query(Project).filter(Project.id == project_id).first()
    project_genre = project.genre if project else None

    result = await svc.auto_extract_debrief(
        chapter_content=narrative_plain,
        chapter_title=chapter.title,
        chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
        character_states=character_states,
        storylines=storylines_data,
        open_promises=open_promises_data,
        genre=project_genre,
    )
    if isinstance(result, dict) and not result.get("error"):
        fpt = result.get("fulfilled_promise_texts") or []
        result["fulfilled_promise_ids"] = enrich_with_promise_ids(fpt, open_promises_data)
        if not cached:
            cached = ChapterDebriefCache(
                project_id=project_id,
                chapter_id=chapter.id,
            )
            db.add(cached)
        cached.content_hash = content_hash
        cached.model_profile = req.model_profile
        cached.llm_provider_id = current_llm_provider
        cached.payload = result
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
    result["cached"] = False
    return result
