"""
chapter_debrief_route.py — 章节复盘提交端点

资源边界：POST /ai/chapter-debrief
业务逻辑（人物/故事线/记忆/资产/伏笔等更新）委托给 debrief_chapter_core 子函数。
"""

from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import (
    Chapter,
    Character,
    ChapterDebriefApplyRecord,
    ChapterDebriefCache,
    ChapterDebriefUndo,
    ChapterIndex,
    MemoryChunk,
    OutlineNode,
    PowerSystem,
    Project,
)
from app.routers.ai.debrief_assets import apply_asset_updates
from app.routers.ai.debrief_chapter_core import (
    apply_character_updates,
    apply_new_characters,
    apply_next_chapter_directives,
    apply_reader_promise_ops,
    apply_speech_kit_updates,
    apply_storyline_updates,
    create_undo_snapshot_if_new,
)
from app.routers.ai.foreshadow import sync_chapter_index_foreshadows
from app.routers.ai.schemas import ChapterDebriefRequest, CharacterUpdate
from app.services.ai.debrief_character_sync import merge_character_updates_for_debrief
from app.routers.ai.text_utils import chapter_debrief_content_hash, plain_text, truncate
from app.routers.outline.helpers.realm_timeline import _build_realm_rank_map
from app.services.ai_service import AIService
from app.services.embedding_service import embed_chunk_async, schedule_background_coro
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block
from app.utils.chapter_numbering import display_chapter_number

logger = logging.getLogger(__name__)
router = APIRouter()


def _ai_profile_from_model_route(model_profile: Optional[str]) -> str:
    """ChapterDebrief / auto-debrief 的 local|gemini → AIService profile。"""
    return "gemini" if (model_profile or "gemini") == "gemini" else "default"


def _resolve_conflict_scan_model(
    req: ChapterDebriefRequest,
    db: Session,
    project_id: str,
    chapter_id: UUID,
) -> tuple[str, Optional[UUID]]:
    """
    记忆冲突检测所用模型：优先请求体，其次本章 ChapterDebriefCache，
    最后默认 gemini。
    """
    if req.model_profile:
        return req.model_profile, req.llm_provider_id
    cached = db.query(ChapterDebriefCache).filter(
        ChapterDebriefCache.project_id == project_id,
        ChapterDebriefCache.chapter_id == chapter_id,
    ).first()
    if cached and (cached.model_profile or "").strip():
        pid: Optional[UUID] = None
        if cached.llm_provider_id:
            try:
                pid = UUID(str(cached.llm_provider_id))
            except (ValueError, TypeError):
                pid = None
        return str(cached.model_profile).strip(), pid
    return "gemini", None


async def _run_conflict_scan_async(
    project_id: str,
    model_profile: str = "gemini",
    llm_provider_id: Optional[UUID] = None,
    *,
    chapter_id: Optional[str] = None,
) -> None:
    """
    复盘完成后后台异步触发记忆冲突检测（fire-and-forget）。

    使用独立 DB session，失败只记录 warning，不影响已提交的复盘数据。
    """
    try:
        from app.services.memory_conflict_detector import detect_memory_conflicts
        ai_profile = _ai_profile_from_model_route(model_profile)
        with SessionLocal() as db:
            svc = AIService(ai_profile, db=db, llm_provider_id=llm_provider_id)
            await detect_memory_conflicts(
                db,
                project_id=project_id,
                ai_service=svc,
                trigger="chapter_debrief",
                chapter_id=chapter_id,
            )
        logger.info("conflict_scan done for project %s", project_id)
    except Exception as exc:
        logger.warning("conflict_scan failed for project %s: %s", project_id, exc)


@router.post("/chapter-debrief")
def chapter_debrief(
    project_id: str,
    req: ChapterDebriefRequest,
    db: Session = Depends(get_db),
):
    """
    章节写完后的「复盘提交」：批量更新人物状态、故事线进展。

    前端在写作页右侧面板提交，避免「写了文章但数据库状态停留在第1章」的空架子问题。
    各业务块委托给 debrief_chapter_core 中的独立函数处理；本函数只负责：
      ① 章节 / 哈希 / apply_source 校验
      ② 调度各处理块
      ③ 章节索引 + ChapterDebriefApplyRecord 写入
      ④ commit + 后台异步任务调度
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    conflict_model_profile, conflict_llm_provider_id = _resolve_conflict_scan_model(
        req, db, project_id, chapter.id,
    )

    plain_for_hash = plain_text(chapter.content or "")
    narrative_for_hash, _ = split_plain_manuscript_and_index_block(plain_for_hash)
    if not narrative_for_hash.strip():
        narrative_for_hash = plain_for_hash.strip()
    content_hash_at_apply = chapter_debrief_content_hash(narrative_for_hash)
    apply_src = req.apply_source or "manual_tab"
    if apply_src not in ("queue_auto", "manual_tab"):
        apply_src = "manual_tab"

    # 同章正文变化后再次复盘：覆盖式清掉旧派生，再落新复盘
    prior_apply = (
        db.query(ChapterDebriefApplyRecord)
        .filter(
            ChapterDebriefApplyRecord.project_id == project_id,
            ChapterDebriefApplyRecord.chapter_id == req.chapter_id,
        )
        .order_by(ChapterDebriefApplyRecord.created_at.desc())
        .first()
    )
    debrief_replacing_prior = bool(
        prior_apply
        and prior_apply.content_hash
        and prior_apply.content_hash != content_hash_at_apply
    )
    if debrief_replacing_prior:
        from app.routers.chapters import clear_chapter_rewrite_derivatives
        clear_chapter_rewrite_derivatives(db, project_id, str(req.chapter_id))

    _project_chars = db.query(Character).filter(Character.project_id == project_id).all()
    create_undo_snapshot_if_new(
        db, project_id, req.chapter_id,
        req.character_updates, req.storyline_updates, _project_chars,
    )

    name_to_rank, _, _ = _build_realm_rank_map(
        db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()
    )

    character_states = [
        {
            "id": str(c.id),
            "name": c.name,
            "current_realm": c.current_realm or "",
            "current_location": c.current_location or "",
            "current_status": c.current_status or "alive",
        }
        for c in _project_chars
    ]
    chapter_index_dict = (
        req.chapter_index.model_dump(exclude_none=True)
        if req.chapter_index is not None
        else None
    )
    merged_char_dicts = merge_character_updates_for_debrief(
        [u.model_dump(exclude_none=True) for u in req.character_updates],
        chapter_index_dict,
        character_states,
    )
    character_updates_to_apply = [
        CharacterUpdate(**row) for row in merged_char_dicts
    ]

    # ── 各业务块并行调度 ────────────────────────────────────────────
    char_result = apply_character_updates(
        db, project_id, character_updates_to_apply,
        req.chapter_id, chapter, name_to_rank, _project_chars,
    )
    updated_chars: List[str] = char_result["updated_chars"]
    realm_rank_warnings: List[str] = char_result["realm_rank_warnings"]
    added_memories: List[str] = char_result["added_memories"]
    _new_memory_chunks: List[MemoryChunk] = char_result["new_memory_chunks"]
    _new_location_entries: list[dict] = char_result["new_location_entries"]

    updated_storylines = apply_storyline_updates(
        db, project_id, req.storyline_updates, req.chapter_id, chapter,
    )
    from app.services.ai.storyline_drift import apply_storyline_weave_actuals

    storyline_drift_report = apply_storyline_weave_actuals(
        db, project_id, chapter, req.storyline_updates,
    )

    # 记忆条目（直接写入，无需外部调用）
    for mu in req.memory_updates:
        content = (mu.content or "").strip()
        if not content:
            continue
        memory = MemoryChunk(
            project_id=project_id,
            chapter_id=req.chapter_id,
            chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
            memory_type=mu.memory_type,
            title=(mu.title or mu.memory_type).strip()[:200],
            content=content,
            tags=mu.tags[:8],
            importance_score=mu.importance_score,
        )
        db.add(memory)
        _new_memory_chunks.append(memory)
        added_memories.append(memory.title or memory.memory_type)

    asset_stats = {
        "created_items": 0, "updated_items": 0,
        "created_skills": 0, "updated_skills": 0,
        "created_factions": 0, "updated_factions": 0,
    }
    if req.asset_updates:
        asset_stats = apply_asset_updates(
            db=db, project_id=project_id,
            chapter=chapter, asset_updates=req.asset_updates,
        )

    chapter_index_saved = False
    chapter_index_error: Optional[str] = None
    synced_foreshadows = {"created": 0, "updated": 0, "resolved": 0}
    nk_in_world: list = []
    nk_protagonist: list = []
    nk_core_events: list = []
    if req.chapter_index:
        try:
            with db.begin_nested():
                hook_strength = max(1, min(5, req.chapter_index.hook_strength or 1))
                index = db.query(ChapterIndex).filter(
                    ChapterIndex.project_id == project_id,
                    ChapterIndex.chapter_id == req.chapter_id,
                ).first()
                data = req.chapter_index.model_dump()
                data.pop("foreshadow_updates", None)
                nk_in_world = list(data.pop("in_world_named_terms", None) or [])
                nk_protagonist = list(data.pop("protagonist_known_terms", None) or [])
                nk_core_events = list(data.get("core_events") or [])
                data["hook_strength"] = hook_strength
                data["chapter_number"] = display_chapter_number(chapter.title, chapter.sort_order)
                if data.get("story_day"):
                    data["story_day"] = truncate(str(data["story_day"]), 100)
                if index:
                    for field, value in data.items():
                        setattr(index, field, value)
                else:
                    index = ChapterIndex(
                        project_id=project_id,
                        chapter_id=req.chapter_id,
                        **data,
                    )
                    db.add(index)
                chapter_index_saved = True
                synced_foreshadows = sync_chapter_index_foreshadows(
                    db, project_id, chapter, req.chapter_index,
                )
        except SQLAlchemyError as exc:
            chapter_index_error = exc.__class__.__name__

    if chapter_index_saved:
        project_row = db.query(Project).filter(Project.id == project_id).first()
        if project_row:
            from app.services.ai.narrative_knowledge import (
                merge_narrative_knowledge_from_debrief,
            )

            merge_narrative_knowledge_from_debrief(
                project_row,
                chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
                in_world_named_terms=nk_in_world,
                protagonist_known_terms=nk_protagonist,
                core_events=nk_core_events,
            )

    added_new_characters = apply_new_characters(
        db, project_id, req.new_characters, req.chapter_id, chapter,
    )

    if req.notes:
        memory = MemoryChunk(
            project_id=project_id,
            chapter_id=req.chapter_id,
            chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
            memory_type="event",
            title="章节复盘备注",
            content=req.notes.strip(),
            tags=["复盘备注"],
            importance_score=0.3,
        )
        db.add(memory)
        _new_memory_chunks.append(memory)
        added_memories.append(memory.title)

    directives_applied = apply_next_chapter_directives(
        db, project_id, req.next_chapter_directives, req.chapter_id, chapter,
    )
    speech_kit_updated_count = apply_speech_kit_updates(
        db, project_id, req.speech_kit_updates, req.chapter_id, chapter,
    )
    promises_created, promises_fulfilled = apply_reader_promise_ops(
        db, project_id,
        req.new_reader_promises,
        req.fulfilled_promise_texts,
        req.fulfilled_promise_ids,
        req.chapter_id,
        chapter,
        outline_node_id=chapter.outline_node_id,
    )

    db.query(ChapterDebriefCache).filter(
        ChapterDebriefCache.project_id == project_id,
        ChapterDebriefCache.chapter_id == chapter.id,
    ).delete(synchronize_session=False)

    new_char_suffix = (
        f"、新配角入库 {len(added_new_characters)} 个（{', '.join(added_new_characters)}）"
        if added_new_characters else ""
    )
    promise_suffix = ""
    if promises_created or promises_fulfilled:
        promise_suffix = f"、读者承诺新增{promises_created}条/兑现{promises_fulfilled}条"
    result_message = (
        f"已更新 {len(updated_chars)} 个人物状态、{len(updated_storylines)} 条故事线、"
        f"{len(added_memories)} 条记忆、章节索引={'已写入' if chapter_index_saved else '未更新'}、"
        f"伏笔管理新增{synced_foreshadows['created']}条/更新{synced_foreshadows['updated']}条/"
        f"回收{synced_foreshadows['resolved']}条、资产新增"
        f"{asset_stats['created_items'] + asset_stats['created_skills'] + asset_stats['created_factions']}条/"
        f"更新{asset_stats['updated_items'] + asset_stats['updated_skills'] + asset_stats['updated_factions']}条"
        f"{new_char_suffix}{promise_suffix}"
    )

    try:
        payload_snapshot = req.model_dump(mode="json")
    except Exception:
        payload_snapshot = {"chapter_id": req.chapter_id, "error": "model_dump_failed"}

    db.add(ChapterDebriefApplyRecord(
        project_id=project_id,
        chapter_id=req.chapter_id,
        apply_source=apply_src,
        content_hash=content_hash_at_apply,
        payload=payload_snapshot,
        result_message=result_message[:8000] if result_message else None,
    ))

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        hint = str(getattr(exc, "orig", None) or exc)
        hint = hint[:500] if hint else exc.__class__.__name__
        raise HTTPException(400, f"章节复盘提交失败：{hint}") from exc

    # 方向2（境界滞后根因修复）：复盘 LLM 抽取之外，用本章章纲 power_milestone 的
    # 「计划境界 floor」确定性兜底推进主角境界（只升不降）。即使 LLM 漏抽境界，记录也会
    # 跟上计划，下一章 draft/质检不再读到滞后值。
    try:
        from app.routers.ai.realm_plan_floor import persist_planned_realm_floor
        _floor_project = db.query(Project).filter(Project.id == chapter.project_id).first()
        if _floor_project is not None:
            _floor_res = persist_planned_realm_floor(db, _floor_project, chapter)
            if _floor_res and _floor_res.get("memory_chunks"):
                _new_memory_chunks.extend(_floor_res["memory_chunks"])
    except Exception:
        logger.exception("realm_plan_floor 兜底推进失败 chapter=%s", req.chapter_id)

    for mc in _new_memory_chunks:
        embed_text = f"{mc.title or ''}\n{mc.content}".strip()
        embed_chunk_async(mc.id, embed_text, SessionLocal)

    if _new_memory_chunks:
        schedule_background_coro(
            _run_conflict_scan_async(
                project_id,
                conflict_model_profile,
                conflict_llm_provider_id,
                chapter_id=str(req.chapter_id),
            )
        )

    if _new_location_entries:
        from app.services.ai.location_debrief import enrich_new_locations
        _chapter_content_for_loc = (chapter.content or "").strip()
        _chapter_title_for_loc = chapter.title or ""
        schedule_background_coro(
            enrich_new_locations(
                project_id=project_id,
                location_entries=_new_location_entries,
                chapter_content=_chapter_content_for_loc,
                chapter_title=_chapter_title_for_loc,
                model_profile=conflict_model_profile,
                llm_provider_id=conflict_llm_provider_id,
            )
        )

    return {
        "ok": True,
        "updated_characters": updated_chars,
        "updated_storylines": updated_storylines,
        "storyline_drift_report": storyline_drift_report,
        "added_memories": added_memories,
        "added_new_characters": added_new_characters,
        "chapter_index_saved": chapter_index_saved,
        "chapter_index_error": chapter_index_error,
        "synced_foreshadows": synced_foreshadows,
        "asset_updates": asset_stats,
        "directives_applied": directives_applied,
        "speech_kit_updated_count": speech_kit_updated_count,
        "promises_created": promises_created,
        "promises_fulfilled": promises_fulfilled,
        "realm_rank_warnings": realm_rank_warnings,
        "replaced_prior_debrief": debrief_replacing_prior,
        "new_locations_detected": len(_new_location_entries),
        "message": result_message,
    }
