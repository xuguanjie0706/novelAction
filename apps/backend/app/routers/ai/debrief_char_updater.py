"""
debrief_char_updater.py — 复盘人物状态更新与撤销快照

提取自 debrief_chapter_core，单独封装：
  - create_undo_snapshot_if_new：首次复盘前记录可回滚快照
  - apply_character_updates：批量更新境界/位置/状态/技能/道具，含审计日志
"""

from __future__ import annotations

from typing import Any, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Character, CharacterChangeLog, ChapterDebriefUndo, MemoryChunk, StoryLine
from app.routers.ai.normalization import normalize_character_status
from app.routers.ai.realm_tracker import (
    apply_realm_progression_side_effects,
    reconcile_character_realm_from_milestones,
    sync_realm_to_arc_stages,
)
from app.routers.outline.helpers.realm_timeline import _rank_for_realm_label
from app.services.ai.character_resolve import resolve_character_for_update
from app.utils.chapter_numbering import display_chapter_number


# ── 撤销快照 ──────────────────────────────────────────────────────

def create_undo_snapshot_if_new(
    db: Session,
    project_id: str,
    chapter_id: UUID,
    character_updates: List[Any],
    storyline_updates: List[Any],
    _project_chars: List[Character],
) -> None:
    """
    若本章尚无撤销快照，记录人物/故事线的当前状态供回滚。

    幂等：同一章存在快照时跳过，不重复创建。
    """
    existing_undo = db.query(ChapterDebriefUndo).filter(
        ChapterDebriefUndo.chapter_id == chapter_id
    ).first()
    if existing_undo:
        return

    char_ids_to_snap: set[str] = set()
    for cu in character_updates:
        resolved = resolve_character_for_update(
            db, project_id, cu.character_id, getattr(cu, "character_name", None),
            characters=_project_chars,
        )
        if resolved:
            char_ids_to_snap.add(str(resolved.id))
    sl_ids_to_snap = {str(su.storyline_id) for su in storyline_updates if su.storyline_id}

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
            sl_statuses_snap.append({"storyline_id": sid, "status": sl.status})

    db.add(ChapterDebriefUndo(
        project_id=project_id,
        chapter_id=chapter_id,
        char_states=char_states_snap,
        storyline_statuses=sl_statuses_snap,
    ))


# ── 人物状态更新 ──────────────────────────────────────────────────

def apply_character_updates(
    db: Session,
    project_id: str,
    character_updates: List[Any],
    chapter_id: UUID,
    chapter: Any,
    name_to_rank: dict,
    _project_chars: List[Character],
) -> dict:
    """
    批量更新人物境界/位置/状态/技能/道具，记录审计日志。

    Returns:
        dict with keys:
          updated_chars: list[str]
          realm_rank_warnings: list[str]
          added_memories: list[str]
          new_memory_chunks: list[MemoryChunk]
          new_location_entries: list[dict]
    """
    updated_chars: list[str] = []
    realm_rank_warnings: list[str] = []
    added_memories: list[str] = []
    new_memory_chunks: list[MemoryChunk] = []
    new_location_entries: list[dict] = []

    for cu in character_updates:
        char = resolve_character_for_update(
            db, project_id, cu.character_id,
            getattr(cu, "character_name", None),
            characters=_project_chars,
        )
        if not char:
            continue

        _before_realm = char.current_realm
        _before_rank = char.realm_rank
        _before_status = char.current_status
        _before_location = char.current_location

        if cu.current_realm is not None:
            raw_realm = cu.current_realm.strip()[:100]
            from app.models import Project
            from app.services.bootstrap.fanqie_normalize import is_fanqie_project
            from app.services.bootstrap.fanqie_realm_policy import (
                normalize_realm_label_for_primary_axis,
            )

            project = db.query(Project).filter(Project.id == project_id).first()
            if project and is_fanqie_project(project) and name_to_rank:
                canonical, norm_warn = normalize_realm_label_for_primary_axis(
                    raw_realm, name_to_rank,
                )
                char.current_realm = canonical[:100]
                if norm_warn:
                    realm_rank_warnings.append(f"{char.name}：{norm_warn}")
            else:
                char.current_realm = raw_realm

        _eff_label = (char.current_realm or "").strip()
        _label_rank = (
            _rank_for_realm_label(_eff_label, name_to_rank)
            if _eff_label and name_to_rank else None
        )
        if _label_rank is not None:
            char.realm_rank = _label_rank
        elif cu.realm_rank is not None:
            _prev_rank = char.realm_rank
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
            else:
                char.realm_rank = cu.realm_rank

        if cu.current_realm is not None or cu.realm_rank is not None:
            realm_label = (
                (cu.current_realm.strip()[:100] if isinstance(cu.current_realm, str) else "")
                or (char.current_realm or "").strip()[:100]
            )
            rank_snap = _rank_for_realm_label(realm_label, name_to_rank) if realm_label and name_to_rank else None
            if rank_snap is None:
                rank_snap = cu.realm_rank if cu.realm_rank is not None else char.realm_rank
            if realm_label or rank_snap is not None:
                chapter_num = display_chapter_number(chapter.title, chapter.sort_order)
                extra = dict(char.extra) if isinstance(char.extra, dict) else {}
                hist = [h for h in (extra.get("debrief_realm_milestones") or []) if isinstance(h, dict)]
                hist = [h for h in hist if int(h.get("chapter_number") or -1) != chapter_num]
                hist.append({
                    "chapter_number": chapter_num,
                    "chapter_id": str(chapter_id),
                    "chapter_title": (chapter.title or "")[:300],
                    "realm_name": realm_label,
                    "realm_rank": rank_snap,
                    "source": "chapter_debrief",
                })
                hist.sort(key=lambda h: int(h.get("chapter_number") or 0))
                extra["debrief_realm_milestones"] = hist
                char.extra = extra
                _realm_mc = apply_realm_progression_side_effects(
                    char,
                    realm_label=realm_label,
                    rank_snap=rank_snap,
                    chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
                    chapter_id=str(chapter_id),
                    chapter_title=chapter.title or "",
                    before_realm=_before_realm,
                    before_rank=_before_rank,
                    project_id=project_id,
                    chapter_uuid=chapter_id,
                    name_to_rank=name_to_rank,
                )
                if _realm_mc is not None:
                    db.add(_realm_mc)
                    new_memory_chunks.append(_realm_mc)
                    added_memories.append(_realm_mc.title)

        if cu.current_location is not None:
            char.current_location = cu.current_location.strip()[:200]
            _loc_name = char.current_location.strip()
            if _loc_name:
                new_location_entries.append({"name": _loc_name, "char_name": char.name})
                # 逐章地点台账（与 debrief_realm_milestones 同模式）：
                # 记录每次复盘时的"章末位置 + 移动原因"，供写章时回溯上一章位置、
                # 校验跨章位置跳转是否合理（防空间漂移）。只在位置真正变化时落账。
                _loc_changed = (_before_location or "").strip() != _loc_name
                if _loc_changed:
                    _loc_chap_num = display_chapter_number(chapter.title, chapter.sort_order)
                    _loc_extra = dict(char.extra) if isinstance(char.extra, dict) else {}
                    _loc_hist = [
                        h for h in (_loc_extra.get("location_milestones") or [])
                        if isinstance(h, dict)
                    ]
                    # 同章重复复盘去重（保留本次）
                    _loc_hist = [
                        h for h in _loc_hist
                        if int(h.get("chapter_number") or -1) != _loc_chap_num
                    ]
                    _loc_hist.append({
                        "chapter_number": _loc_chap_num,
                        "chapter_id": str(chapter_id),
                        "chapter_title": (chapter.title or "")[:300],
                        "location": _loc_name,
                        "from_location": (_before_location or "").strip()[:200] or None,
                        "reason": (cu.location_change_reason or "").strip()[:500] or None,
                        "source": "chapter_debrief",
                    })
                    _loc_hist.sort(key=lambda h: int(h.get("chapter_number") or 0))
                    _loc_extra["location_milestones"] = _loc_hist
                    char.extra = _loc_extra

        if cu.current_status is not None:
            normalized_status = normalize_character_status(cu.current_status)
            if normalized_status:
                char.current_status = normalized_status

        _added_skill_name = None
        if cu.add_skill:
            skills = list(char.known_skills or [])
            skill_with_source = {**cu.add_skill, "from_chapter_id": str(chapter_id)}
            existing_ids = {s.get("skill_id") for s in skills if isinstance(s, dict)}
            if cu.add_skill.get("skill_id") in existing_ids:
                skills = [
                    {**s, "mastery": cu.add_skill.get("mastery", s.get("mastery")),
                     "from_chapter_id": str(chapter_id)}
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
                item_with_source = {**cu.add_item, "from_chapter_id": str(chapter_id)}
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

        if reconcile_character_realm_from_milestones(char, name_to_rank):
            _chap_num_rec = display_chapter_number(chapter.title, chapter.sort_order)
            sync_label = (char.current_realm or "").strip()
            if sync_label:
                sync_realm_to_arc_stages(
                    char=char,
                    realm_label=sync_label,
                    chapter_number=_chap_num_rec,
                    chapter_id=str(chapter_id),
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
                chapter_id=chapter_id,
                chapter_number=_chapter_num_str,
                chapter_title=chapter.title or "",
                source="debrief",
                summary="、".join(_summary_parts),
                changes=_audit_changes,
            ))

        updated_chars.append(char.name)

    return {
        "updated_chars": updated_chars,
        "realm_rank_warnings": realm_rank_warnings,
        "added_memories": added_memories,
        "new_memory_chunks": new_memory_chunks,
        "new_location_entries": new_location_entries,
    }
