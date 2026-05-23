#!/usr/bin/env python3
"""
补跑复盘 payload 中因 AI slug character_id 被丢弃的人物更新。

用法（项目根目录）：
  cd apps/backend && source .venv/bin/activate
  python scripts/backfill_missed_debrief_characters.py --project-id <uuid> [--from-chapter 23]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Character, CharacterChangeLog, Chapter, ChapterDebriefApplyRecord, PowerSystem
from app.services.ai.character_resolve import resolve_character_for_update
from app.routers.ai.normalization import normalize_character_status
from app.routers.ai.realm_tracker import apply_realm_progression_side_effects
from app.routers.outline.helpers.realm_timeline import _build_realm_rank_map, _rank_for_realm_label
from app.utils.chapter_numbering import display_chapter_number


def _apply_cu(db, project_id: str, chapter: Chapter, cu: dict, project_chars, name_to_rank) -> bool:
    char = resolve_character_for_update(
        db,
        project_id,
        cu.get("character_id"),
        cu.get("character_name"),
        characters=project_chars,
    )
    if not char:
        return False

    ch_num = display_chapter_number(chapter.title, chapter.sort_order)
    existing_log = (
        db.query(CharacterChangeLog.id)
        .filter(
            CharacterChangeLog.project_id == project_id,
            CharacterChangeLog.character_id == char.id,
            CharacterChangeLog.chapter_id == chapter.id,
            CharacterChangeLog.source == "debrief",
        )
        .first()
    )
    if existing_log:
        return False

    _before_realm = char.current_realm
    _before_status = char.current_status
    _before_location = char.current_location
    _audit: list[dict] = []

    if cu.get("current_realm"):
        char.current_realm = str(cu["current_realm"]).strip()[:100]
    if cu.get("realm_rank") is not None:
        try:
            new_rank = int(cu["realm_rank"])
            prev = char.realm_rank or 0
            if new_rank >= prev or (char.current_status or "alive") in {"depowered", "suppressed", "sealed"}:
                char.realm_rank = new_rank
        except (TypeError, ValueError):
            pass

    if char.realm_rank is None and name_to_rank and (char.current_realm or "").strip():
        rr = _rank_for_realm_label(char.current_realm.strip(), name_to_rank)
        if rr is not None:
            char.realm_rank = rr

    realm_label = (cu.get("current_realm") or char.current_realm or "").strip()[:100]
    rank_snap = cu.get("realm_rank") if cu.get("realm_rank") is not None else char.realm_rank
    if rank_snap is None and name_to_rank and realm_label:
        rank_snap = _rank_for_realm_label(realm_label, name_to_rank)

    if realm_label or rank_snap is not None:
        ch_num = display_chapter_number(chapter.title, chapter.sort_order)
        extra = dict(char.extra) if isinstance(char.extra, dict) else {}
        hist = [h for h in (extra.get("debrief_realm_milestones") or []) if isinstance(h, dict)]
        hist = [h for h in hist if int(h.get("chapter_number") or -1) != ch_num]
        hist.append({
            "chapter_number": ch_num,
            "chapter_id": str(chapter.id),
            "chapter_title": (chapter.title or "")[:300],
            "realm_name": realm_label,
            "realm_rank": rank_snap,
            "source": "chapter_debrief",
        })
        hist.sort(key=lambda h: int(h.get("chapter_number") or 0))
        extra["debrief_realm_milestones"] = hist
        char.extra = extra
        apply_realm_progression_side_effects(
            char,
            realm_label=realm_label,
            rank_snap=rank_snap,
            chapter_number=ch_num,
            chapter_id=str(chapter.id),
            chapter_title=chapter.title or "",
            before_realm=_before_realm,
            before_rank=char.realm_rank,
            project_id=project_id,
            chapter_uuid=chapter.id,
            name_to_rank=name_to_rank,
        )

    if cu.get("current_location"):
        char.current_location = str(cu["current_location"]).strip()[:200]
    if cu.get("current_status"):
        st = normalize_character_status(cu["current_status"])
        if st:
            char.current_status = st

    add_skill = cu.get("add_skill")
    if isinstance(add_skill, dict) and add_skill.get("skill_name"):
        skills = list(char.known_skills or [])
        skills.append({**add_skill, "from_chapter_id": str(chapter.id)})
        char.known_skills = skills

    if str(_before_realm or "") != str(char.current_realm or ""):
        _audit.append({"field": "current_realm", "label": "境界", "before": _before_realm, "after": char.current_realm})
    if str(_before_status or "") != str(char.current_status or ""):
        _audit.append({"field": "current_status", "label": "状态", "before": _before_status, "after": char.current_status})
    if str(_before_location or "") != str(char.current_location or ""):
        _audit.append({"field": "current_location", "label": "位置", "before": _before_location, "after": char.current_location})

    if _audit:
        ch_num_str = str(display_chapter_number(chapter.title, chapter.sort_order))
        summary_parts = []
        for c in _audit:
            if c["before"] and c["after"]:
                summary_parts.append(f"{c['label']} {c['before']}→{c['after']}")
            elif c["after"]:
                summary_parts.append(f"{c['label']}：{c['after']}")
        db.add(CharacterChangeLog(
            project_id=project_id,
            character_id=char.id,
            character_name=char.name,
            chapter_id=chapter.id,
            chapter_number=ch_num_str,
            chapter_title=chapter.title or "",
            source="debrief",
            summary="、".join(summary_parts),
            changes=_audit,
        ))
    return bool(_audit) or realm_label != (_before_realm or "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--from-chapter", type=int, default=1)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        pid = args.project_id
        project_chars = db.query(Character).filter(Character.project_id == pid).all()
        name_to_rank, _, _ = _build_realm_rank_map(
            db.query(PowerSystem).filter(PowerSystem.project_id == pid).all()
        )
        records = (
            db.query(ChapterDebriefApplyRecord, Chapter)
            .join(Chapter, Chapter.id == ChapterDebriefApplyRecord.chapter_id)
            .filter(ChapterDebriefApplyRecord.project_id == pid)
            .order_by(Chapter.sort_order)
            .all()
        )
        applied = 0
        for rec, chapter in records:
            ch_no = chapter.sort_order + 1
            if ch_no < args.from_chapter:
                continue
            payload = rec.payload or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            for cu in payload.get("character_updates") or []:
                if not isinstance(cu, dict):
                    continue
                raw_id = str(cu.get("character_id") or "")
                try:
                    UUID(raw_id)
                    already_uuid = True
                except Exception:
                    already_uuid = False
                if already_uuid:
                    continue
                if _apply_cu(db, pid, chapter, cu, project_chars, name_to_rank):
                    applied += 1
                    print(f"  ✓ ch{ch_no} {cu.get('character_id')} → applied")
        db.commit()
        print(f"Done. applied={applied}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
