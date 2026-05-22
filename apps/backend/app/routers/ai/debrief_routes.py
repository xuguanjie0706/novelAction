import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import (
    Chapter,
    ChapterDebriefApplyRecord,
    ChapterDebriefCache,
    ChapterDebriefUndo,
    ChapterIndex,
    Character,
    CharacterChangeLog,
    MemoryChunk,
    OutlineNode,
    PowerSystem,
    ReaderPromise,
    StoryLine,
)
from app.services.ai_service import AIService
from app.services.embedding_service import embed_chunk_async, schedule_background_coro
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block
from app.utils.chapter_numbering import display_chapter_number
from app.routers.ai.debrief_assets import apply_asset_updates
from app.routers.ai.foreshadow import sync_chapter_index_foreshadows
from app.routers.ai.normalization import normalize_character_status, normalize_storyline_status
from app.routers.ai.realm_tracker import (
    apply_realm_progression_side_effects,
    reconcile_character_realm_from_milestones,
    sync_realm_to_arc_stages,
)
from app.routers.outline.helpers.realm_timeline import _build_realm_rank_map, _rank_for_realm_label
from app.routers.ai.schemas import AutoDebriefRequest, ChapterDebriefRequest
from app.services.ai.promise_debrief import (
    apply_fulfilled_by_ids,
    apply_plan_promise_fulfillment,
    enrich_with_promise_ids,
)
from app.routers.ai.text_utils import chapter_debrief_content_hash, plain_text, truncate

logger = logging.getLogger(__name__)


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
    记忆冲突检测所用模型：优先请求体，其次本章 ChapterDebriefCache（auto-debrief 写入），
    最后默认 gemini（管理后台默认远程线路）。
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

    使用独立 DB session 避免与主请求 session 竞争；
    失败只记录 warning，不影响已提交的复盘数据。

    model_profile / llm_provider_id 应与本章 auto-debrief、门控写作所选线路一致。
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
    except Exception as exc:  # noqa: BLE001
        logger.warning("conflict_scan failed for project %s: %s", project_id, exc)

router = APIRouter()


@router.post("/chapter-debrief")
def chapter_debrief(
    project_id: str,
    req: ChapterDebriefRequest,
    db: Session = Depends(get_db),
):
    """
    章节写完后的「复盘提交」：批量更新人物状态、故事线进展。
    前端在写作页右侧面板提交，避免「写了文章但数据库状态停留在第1章」的空架子问题。
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

    # 同章正文变化后再次复盘：覆盖式清掉旧派生（记忆/情节档案/伏笔/承诺等），再落新复盘
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

    updated_chars: List[str] = []
    updated_storylines: List[str] = []
    added_memories: List[str] = []
    _new_memory_chunks: List[MemoryChunk] = []
    chapter_index_saved = False
    chapter_index_error: Optional[str] = None
    # 境界序号单调性 guard：收集被阻止的降级操作，回传给前端提示作者检查
    realm_rank_warnings: List[str] = []
    synced_foreshadows = {"created": 0, "updated": 0, "resolved": 0}
    directives_applied = 0
    speech_kit_updated_count = 0
    promises_created = 0
    promises_fulfilled = 0
    asset_stats = {
        "created_items": 0,
        "updated_items": 0,
        "created_skills": 0,
        "updated_skills": 0,
        "created_factions": 0,
        "updated_factions": 0,
    }

    existing_undo = db.query(ChapterDebriefUndo).filter(
        ChapterDebriefUndo.chapter_id == req.chapter_id
    ).first()
    if not existing_undo:
        char_ids_to_snap = {str(cu.character_id) for cu in req.character_updates if cu.character_id}
        sl_ids_to_snap = {str(su.storyline_id) for su in req.storyline_updates if su.storyline_id}

        char_states_snap = []
        for cid in char_ids_to_snap:
            try:
                cid_uuid = UUID(cid)
            except Exception:
                continue
            c = db.query(Character).filter(
                Character.id == cid_uuid, Character.project_id == project_id
            ).first()
            if c:
                char_states_snap.append({
                    "character_id": cid,
                    "current_realm": c.current_realm,
                    "current_location": c.current_location,
                    "current_status": c.current_status,
                    "realm_rank": c.realm_rank,
                })

        sl_statuses_snap = []
        for sid in sl_ids_to_snap:
            try:
                sid_uuid = UUID(sid)
            except Exception:
                continue
            sl = db.query(StoryLine).filter(
                StoryLine.id == sid_uuid, StoryLine.project_id == project_id
            ).first()
            if sl:
                sl_statuses_snap.append({
                    "storyline_id": sid,
                    "status": sl.status,
                })

        undo_row = ChapterDebriefUndo(
            project_id=project_id,
            chapter_id=req.chapter_id,
            char_states=char_states_snap,
            storyline_statuses=sl_statuses_snap,
        )
        db.add(undo_row)

    name_to_rank, _, _ = _build_realm_rank_map(
        db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()
    )

    for cu in req.character_updates:
        try:
            _ = UUID(str(cu.character_id))
        except Exception:
            continue

        char = db.query(Character).filter(
            Character.id == cu.character_id,
            Character.project_id == project_id,
        ).first()
        if not char:
            continue

        _before_realm = char.current_realm
        _before_rank = char.realm_rank
        _before_status = char.current_status
        _before_location = char.current_location

        if cu.current_realm is not None:
            char.current_realm = cu.current_realm.strip()[:100]
        if cu.realm_rank is not None:
            _prev_rank = char.realm_rank
            # ── 境界序号单调性 guard ────────────────────────────────────────
            # 防止 AI 复盘把主角/重要角色境界序号降低（如主角从 rank 5 写成 rank 2）。
            # 豁免：角色当前状态为 depowered / suppressed / sealed（剧情性强制降级）。
            _blocked_statuses = {"depowered", "suppressed", "sealed"}
            if (
                _prev_rank is not None
                and cu.realm_rank < _prev_rank
                and (char.current_status or "alive") not in _blocked_statuses
            ):
                realm_rank_warnings.append(
                    f"⚠️ {char.name} 境界序号 {_prev_rank}（{char.current_realm or '?'}）"
                    f"→ {cu.realm_rank} 为降级，已自动阻止；"
                    "若确为剧情性降级（封印/剥夺），请先将角色状态设为 'suppressed' 后重试。"
                )
                # 阻止写入：保留当前 realm_rank，仅更新 realm 名称
            else:
                char.realm_rank = cu.realm_rank

        if char.realm_rank is None and name_to_rank and (char.current_realm or "").strip():
            _resolved_rank = _rank_for_realm_label((char.current_realm or "").strip(), name_to_rank)
            if _resolved_rank is not None:
                char.realm_rank = _resolved_rank

        if cu.current_realm is not None or cu.realm_rank is not None:
            realm_label = (
                (cu.current_realm.strip()[:100] if isinstance(cu.current_realm, str) else "")
                or (char.current_realm or "").strip()[:100]
            )
            rank_snap = cu.realm_rank if cu.realm_rank is not None else char.realm_rank
            if rank_snap is None and name_to_rank and realm_label:
                rank_snap = _rank_for_realm_label(realm_label, name_to_rank)
            if realm_label or rank_snap is not None:
                chapter_num = display_chapter_number(chapter.title, chapter.sort_order)
                extra = dict(char.extra) if isinstance(char.extra, dict) else {}
                hist = [h for h in (extra.get("debrief_realm_milestones") or []) if isinstance(h, dict)]
                hist = [h for h in hist if int(h.get("chapter_number") or -1) != chapter_num]
                hist.append(
                    {
                        "chapter_number": chapter_num,
                        "chapter_id": str(req.chapter_id),
                        "chapter_title": (chapter.title or "")[:300],
                        "realm_name": realm_label,
                        "realm_rank": rank_snap,
                        "source": "chapter_debrief",
                    }
                )
                hist.sort(key=lambda h: int(h.get("chapter_number") or 0))
                extra["debrief_realm_milestones"] = hist
                char.extra = extra
                _chap_num_ms = display_chapter_number(chapter.title, chapter.sort_order)
                _realm_mc_from_ms = apply_realm_progression_side_effects(
                    char,
                    realm_label=realm_label,
                    rank_snap=rank_snap,
                    chapter_number=_chap_num_ms,
                    chapter_id=str(req.chapter_id),
                    chapter_title=chapter.title or "",
                    before_realm=_before_realm,
                    before_rank=_before_rank,
                    project_id=project_id,
                    chapter_uuid=req.chapter_id,
                    name_to_rank=name_to_rank,
                )
                if _realm_mc_from_ms is not None:
                    db.add(_realm_mc_from_ms)
                    _new_memory_chunks.append(_realm_mc_from_ms)
                    added_memories.append(_realm_mc_from_ms.title)
        if cu.current_location is not None:
            char.current_location = cu.current_location.strip()[:200]
        if cu.current_status is not None:
            normalized_status = normalize_character_status(cu.current_status)
            if normalized_status:
                char.current_status = normalized_status

        _added_skill_name = None
        if cu.add_skill:
            skills = list(char.known_skills or [])
            skill_with_source = {**cu.add_skill, "from_chapter_id": str(req.chapter_id)}
            existing_ids = {s.get("skill_id") for s in skills if isinstance(s, dict)}
            if cu.add_skill.get("skill_id") in existing_ids:
                skills = [
                    {**s, "mastery": cu.add_skill.get("mastery", s.get("mastery")),
                     "from_chapter_id": str(req.chapter_id)}
                    if isinstance(s, dict) and s.get("skill_id") == cu.add_skill.get("skill_id")
                    else s
                    for s in skills
                ]
            else:
                skills.append(skill_with_source)
                _added_skill_name = cu.add_skill.get("skill_name") or cu.add_skill.get("add_skill_name")
            char.known_skills = skills

        _added_item_name = None
        if cu.add_item:
            items = list(char.owned_items or [])
            existing_item_ids = {i.get("item_id") for i in items if isinstance(i, dict)}
            if cu.add_item.get("item_id") not in existing_item_ids:
                item_with_source = {**cu.add_item, "from_chapter_id": str(req.chapter_id)}
                items.append(item_with_source)
                _added_item_name = cu.add_item.get("item_name") or cu.add_item.get("add_item_name")
            char.owned_items = items

        _removed_item_name = None
        if cu.remove_item_id:
            _removed = next(
                (i for i in (char.owned_items or [])
                 if isinstance(i, dict) and i.get("item_id") == cu.remove_item_id),
                None,
            )
            _removed_item_name = (_removed or {}).get("item_name") if _removed else None
            char.owned_items = [
                i for i in (char.owned_items or [])
                if not (isinstance(i, dict) and i.get("item_id") == cu.remove_item_id)
            ]

        # 复盘未带境界字段时，用全书 milestone 快照抬升 current_realm（历史数据自愈）
        if reconcile_character_realm_from_milestones(char, name_to_rank):
            _chap_num_rec = display_chapter_number(chapter.title, chapter.sort_order)
            sync_label = (char.current_realm or "").strip()
            if sync_label:
                sync_realm_to_arc_stages(
                    char=char,
                    realm_label=sync_label,
                    chapter_number=_chap_num_rec,
                    chapter_id=str(req.chapter_id),
                    chapter_title=chapter.title or "",
                )

        _audit_changes = []
        if cu.current_realm is not None and str(_before_realm or "") != str(char.current_realm or ""):
            _audit_changes.append({"field": "current_realm", "label": "境界",
                                    "before": _before_realm, "after": char.current_realm})
        if cu.current_status is not None and str(_before_status or "") != str(char.current_status or ""):
            _audit_changes.append({"field": "current_status", "label": "状态",
                                    "before": _before_status, "after": char.current_status})
        if cu.current_location is not None and str(_before_location or "") != str(char.current_location or ""):
            _audit_changes.append({"field": "current_location", "label": "位置",
                                    "before": _before_location, "after": char.current_location})
        if _added_skill_name:
            _audit_changes.append({"field": "skill_gained", "label": "习得技能",
                                    "before": None, "after": _added_skill_name})
        if _added_item_name:
            _audit_changes.append({"field": "item_gained", "label": "获得道具",
                                    "before": None, "after": _added_item_name})
        if _removed_item_name:
            _audit_changes.append({"field": "item_lost", "label": "失去道具",
                                    "before": _removed_item_name, "after": None})

        if _audit_changes:
            _chapter_num_str = str(display_chapter_number(chapter.title, chapter.sort_order))
            _summary_parts = []
            for c in _audit_changes:
                if c["before"] and c["after"]:
                    _summary_parts.append(f"{c['label']} {c['before']}→{c['after']}")
                elif c["after"]:
                    _summary_parts.append(f"{c['label']}：{c['after']}")
                elif c["before"]:
                    _summary_parts.append(f"失去{c['label']}：{c['before']}")
            db.add(CharacterChangeLog(
                project_id=project_id,
                character_id=char.id,
                character_name=char.name,
                chapter_id=req.chapter_id,
                chapter_number=_chapter_num_str,
                chapter_title=chapter.title or "",
                source="debrief",
                summary="、".join(_summary_parts),
                changes=_audit_changes,
            ))

        updated_chars.append(char.name)

    for su in req.storyline_updates:
        storyline_uuid = None
        if su.storyline_id:
            try:
                storyline_uuid = UUID(str(su.storyline_id))
            except Exception:
                storyline_uuid = None

        if storyline_uuid:
            sl = db.query(StoryLine).filter(
                StoryLine.id == storyline_uuid,
                StoryLine.project_id == project_id,
            ).first()
        elif su.storyline_name:
            sl = db.query(StoryLine).filter(
                StoryLine.name == su.storyline_name,
                StoryLine.project_id == project_id,
            ).first()
        else:
            continue

        if not sl:
            continue

        if su.status is not None:
            normalized_storyline_status = normalize_storyline_status(su.status)
            if normalized_storyline_status:
                sl.status = normalized_storyline_status
        if su.append_beat:
            beats = list(sl.key_beats or [])
            chapter_key = str(req.chapter_id)
            # 同章再次复盘时替换该章 beat，避免重写后故事线节点重复堆叠
            beats = [
                b for b in beats
                if not (isinstance(b, dict) and b.get("chapter_id") == chapter_key)
            ]
            beats.append({
                "chapter": display_chapter_number(chapter.title, chapter.sort_order),
                "chapter_title": chapter.title,
                "beat": su.append_beat,
                "chapter_id": chapter_key,
            })
            sl.key_beats = beats

        updated_storylines.append(sl.name)

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

    if req.asset_updates:
        asset_stats = apply_asset_updates(
            db=db,
            project_id=project_id,
            chapter=chapter,
            asset_updates=req.asset_updates,
        )

    if req.chapter_index:
        try:
            with db.begin_nested():
                hook_strength = max(1, min(5, req.chapter_index.hook_strength or 1))
                index = db.query(ChapterIndex).filter(
                    ChapterIndex.project_id == project_id,
                    ChapterIndex.chapter_id == req.chapter_id,
                ).first()
                data = req.chapter_index.model_dump()
                # ChapterIndex ORM 不接收中间态字段，只落库拆分后的结果字段。
                data.pop("foreshadow_updates", None)
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
                    db,
                    project_id,
                    chapter,
                    req.chapter_index,
                )
        except SQLAlchemyError as exc:
            chapter_index_error = exc.__class__.__name__

    added_new_characters: List[str] = []
    if req.new_characters:
        existing_names = {
            c.name for c in db.query(Character.name).filter(
                Character.project_id == project_id
            ).all()
        }
        chapter_num = display_chapter_number(chapter.title, chapter.sort_order)
        _VALID_TIERS = {"core", "arc", "plot", "background"}
        _ARC_SCOPE_TO_TIER = {
            "single_chapter": "plot",
            "mini_arc": "arc",
            "long_arc": "core",
        }
        for nc in req.new_characters:
            stored_name = truncate((nc.name or "").strip(), 100)
            if not stored_name or stored_name in existing_names:
                continue
            tier = nc.character_tier if nc.character_tier in _VALID_TIERS else None
            if tier is None:
                tier = _ARC_SCOPE_TO_TIER.get(nc.arc_scope or "", "arc")
            new_char_id = uuid4()
            new_char = Character(
                id=new_char_id,
                project_id=project_id,
                name=stored_name,
                role=truncate(nc.role or "supporting", 20),
                character_tier=tier,
                gender=truncate(nc.gender, 20) if nc.gender else None,
                age=truncate(nc.age, 50) if nc.age else None,
                faction=truncate(nc.faction, 100) if nc.faction else None,
                personality=nc.personality,
                motivation=nc.motivation,
                background=nc.background,
                current_realm=truncate(nc.current_realm, 100) if nc.current_realm else None,
                current_status=normalize_character_status(nc.current_status) or "alive",
                current_location=truncate(nc.current_location, 200) if nc.current_location else None,
                author_notes=nc.author_notes,
                extra={"first_appearance_chapter": chapter_num, "arc_scope": nc.arc_scope},
            )
            db.add(new_char)
            # 先落库人物行，再挂审计日志，避免同一事务内 INSERT 顺序导致
            # character_change_logs_character_id_fkey 校验失败。
            db.flush()

            _tier_labels = {
                "core": "核心长线", "arc": "弧线支柱",
                "plot": "剧情推手", "background": "背景填充",
            }
            db.add(CharacterChangeLog(
                project_id=project_id,
                character_id=new_char_id,
                character_name=new_char.name,
                chapter_id=req.chapter_id,
                chapter_number=str(chapter_num),
                chapter_title=chapter.title or "",
                source="debrief",
                summary=f"首次登场 · {_tier_labels.get(tier, tier)}",
                changes=[{
                    "field": "created",
                    "label": "首次入库",
                    "before": None,
                    "after": _tier_labels.get(tier, tier),
                }],
            ))

            existing_names.add(stored_name)
            added_new_characters.append(stored_name)

    if req.notes:
        memory = MemoryChunk(
            project_id=project_id,
            chapter_id=req.chapter_id,
            chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
            memory_type="event",
            title="章节复盘备注",
            content=req.notes.strip(),
            tags=["复盘备注"],
            importance_score=0.3,  # 作者备注属辅助信息，优先级低于正文事件记忆
        )
        db.add(memory)
        _new_memory_chunks.append(memory)
        added_memories.append(memory.title)

    # 复盘闭环：下一章 patch / 语风 / 读者承诺（须在 commit 前完成）
    if req.next_chapter_directives:
        for d in req.next_chapter_directives:
            try:
                target_id = d.get("outline_node_id")
                patch = d.get("patch") or {}
                if not patch:
                    continue
                node = None
                if target_id:
                    try:
                        node = db.query(OutlineNode).filter(
                            OutlineNode.id == UUID(str(target_id)),
                            OutlineNode.project_id == project_id
                        ).first()
                    except Exception:
                        node = None
                if not node:
                    current_sort = chapter.sort_order or 0
                    node = db.query(OutlineNode).filter(
                        OutlineNode.project_id == project_id,
                        OutlineNode.sort_order > current_sort,
                        OutlineNode.status != "done"
                    ).order_by(OutlineNode.sort_order.asc()).first()
                if node:
                    extra = dict(node.extra or {})
                    prev = extra.get("directives_from_prev") or []
                    prev.append({
                        "from_chapter_id": str(req.chapter_id),
                        "from_chapter_title": chapter.title,
                        "patch": patch,
                        "reason": d.get("reason", ""),
                        "applied_at": "now"
                    })
                    extra["directives_from_prev"] = prev[-5:]
                    node.extra = extra
                    directives_applied += 1
            except Exception:
                continue

    if req.speech_kit_updates:
        for sku in req.speech_kit_updates:
            try:
                cid = sku.get("character_id")
                if not cid:
                    continue
                char = db.query(Character).filter(
                    Character.id == UUID(str(cid)),
                    Character.project_id == project_id
                ).first()
                if not char:
                    continue
                kit = dict(char.speech_kit or {})
                old_words = set(kit.get("signature_words") or [])
                new_words = [w.strip() for w in (sku.get("new_signature_words") or []) if w.strip()]
                kit["signature_words"] = list(old_words | set(new_words))[:8]
                old_dialogues = kit.get("sample_dialogues") or []
                new_dialogues = [d.strip() for d in (sku.get("new_sample_dialogues") or []) if d.strip()]
                kit["sample_dialogues"] = (old_dialogues + new_dialogues)[-8:]
                if sku.get("evolution_note"):
                    notes = kit.get("recent_evolution_notes") or []
                    notes.append({
                        "chapter_id": str(req.chapter_id),
                        "chapter_title": chapter.title,
                        "note": sku["evolution_note"][:200]
                    })
                    kit["recent_evolution_notes"] = notes[-5:]
                char.speech_kit = kit
                speech_kit_updated_count += 1
            except Exception:
                continue

    if req.new_reader_promises:
        for p in req.new_reader_promises:
            try:
                text = (p.get("promise_text") or "").strip()
                if not text:
                    continue
                rp = ReaderPromise(
                    project_id=project_id,
                    promise_text=text[:500],
                    promise_type=p.get("promise_type", "chapter_ending"),
                    source_chapter_id=req.chapter_id,
                    source_chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
                    expected_chapter_window=int(p.get("expected_within_chapters") or 3),
                    priority=int(p.get("priority") or 3),
                    audience_aware=int(p.get("audience_aware") or 3),
                    status="open",
                )
                db.add(rp)
                promises_created += 1
            except Exception:
                continue

    if req.fulfilled_promise_texts:
        def _fuzzy_match(query: str, target: str, ngram: int = 4) -> bool:
            if query in target or target[:20] in query:
                return True
            if len(query) >= ngram:
                for i in range(len(query) - ngram + 1):
                    if query[i:i + ngram] in target:
                        return True
            return False

        open_promises = (
            db.query(ReaderPromise)
            .filter(
                ReaderPromise.project_id == project_id,
                ReaderPromise.status == "open",
            )
            .all()
        )
        for promise in open_promises:
            for ft in req.fulfilled_promise_texts:
                ft = ft.strip()
                if ft and _fuzzy_match(ft, promise.promise_text or ""):
                    promise.status = "fulfilled"
                    promise.fulfilled_chapter_id = req.chapter_id
                    promise.fulfilled_chapter_number = chapter.sort_order
                    promises_fulfilled += 1
                    break

    # ── 承诺兑现：精确 ID 匹配（优先级高于文本模糊匹配，避免误判）────────────
    # fulfilled_promise_ids 由 auto_debrief 服务端解析后写入缓存，前端原样回传。
    if req.fulfilled_promise_ids:
        id_fulfilled = apply_fulfilled_by_ids(
            db, project_id, req.chapter_id,
            chapter.sort_order or 0, req.fulfilled_promise_ids,
        )
        promises_fulfilled += id_fulfilled

    # ── 承诺兑现：规划层兜底（章纲 promise_fulfilled → ReaderPromise）──────────
    # Bootstrap Step 12.5 在 OutlineNode.extra.promise_fulfilled 里写入「本章
    # 计划兑现的承诺关键词」，但该字段此前仅供大纲 Linter 检查，未与 DB 联动。
    # 此处在每次复盘提交时读取并落库，连通规划层与运行层的承诺闭环。
    plan_fulfilled = apply_plan_promise_fulfillment(
        db, project_id, req.chapter_id,
        chapter.sort_order or 0,
        outline_node_id=chapter.outline_node_id,
    )
    promises_fulfilled += plan_fulfilled

    db.query(ChapterDebriefCache).filter(
        ChapterDebriefCache.project_id == project_id,
        ChapterDebriefCache.chapter_id == chapter.id,
    ).delete(synchronize_session=False)

    new_char_suffix = f"、新配角入库 {len(added_new_characters)} 个（{', '.join(added_new_characters)}）" if added_new_characters else ""
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

    for mc in _new_memory_chunks:
        embed_text = f"{mc.title or ''}\n{mc.content}".strip()
        embed_chunk_async(mc.id, embed_text, SessionLocal)

    # 有新记忆写入时，后台触发记忆冲突检测（sync 路由经主 loop 跨线程提交）
    if _new_memory_chunks:
        schedule_background_coro(
            _run_conflict_scan_async(
                project_id,
                conflict_model_profile,
                conflict_llm_provider_id,
                chapter_id=str(req.chapter_id),
            )
        )

    return {
        "ok": True,
        "updated_characters": updated_chars,
        "updated_storylines": updated_storylines,
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
        # 被境界序号单调性 guard 阻止的降级操作；非空时前端应弹出警告提示作者检查复盘
        "realm_rank_warnings": realm_rank_warnings,
        "replaced_prior_debrief": debrief_replacing_prior,
        "message": result_message,
    }


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

    请求体 `cache_only=true` 时：仅返回与当前正文哈希一致的 ChapterDebriefCache，
    不调用 LLM；无缓存时返回空建议且 `cache_only_miss=true`（供写作页打开复盘 Tab 恢复展示）。
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
    cache_hit = (
        cached
        and not req.force_refresh
        and cached.content_hash == content_hash
        and cached.model_profile == req.model_profile
        and (cached.llm_provider_id or None) == current_llm_provider
        and isinstance(cached.payload, dict)
    )
    if cache_hit:
        payload = dict(cached.payload)
        payload["cached"] = True
        return payload

    if req.cache_only:
        # 无可用缓存：不调用 LLM，返回空建议供前端保持表单/提示用户手动「AI 分析」
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

    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()
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
        StoryLine.status.in_(["planned", "active", "climax"])
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

    # 查询当前 open 承诺，注入 AI 以支持兑现检测
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

    result = await svc.auto_extract_debrief(
        chapter_content=narrative_plain,
        chapter_title=chapter.title,
        chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
        character_states=character_states,
        storylines=storylines_data,
        open_promises=open_promises_data,
    )
    if isinstance(result, dict) and not result.get("error"):
        # 服务端将 fulfilled_promise_texts 解析为精确 ID 并写入缓存，
        # 前端提交 chapter_debrief 时带上 fulfilled_promise_ids 可跳过模糊匹配。
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
