#!/usr/bin/env python3
"""
按章顺序，用 chapter_index.core_events 补写 characters 表（修复复盘漏交 character_updates）。

用法：
  cd apps/backend && source .venv/bin/activate
  python scripts/sync_characters_from_chapter_indexes.py --project-id <uuid> [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import Chapter, ChapterIndex, Character, PowerSystem
from app.services.ai.debrief_character_sync import merge_character_updates_for_debrief
from app.routers.outline.helpers.realm_timeline import _build_realm_rank_map
from scripts.backfill_missed_debrief_characters import _apply_cu


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    pid = args.project_id

    db = SessionLocal()
    try:
        project_chars = db.query(Character).filter(Character.project_id == pid).all()
        name_to_rank, _, _ = _build_realm_rank_map(
            db.query(PowerSystem).filter(PowerSystem.project_id == pid).all()
        )
        rows = (
            db.query(ChapterIndex, Chapter)
            .join(Chapter, Chapter.id == ChapterIndex.chapter_id)
            .filter(ChapterIndex.project_id == pid, Chapter.project_id == pid)
            .order_by(Chapter.sort_order)
            .all()
        )
        if not rows:
            print("No chapter_indexes found.")
            return

        applied_total = 0
        for idx, chapter in rows:
            ch_no = (chapter.sort_order or 0) + 1
            body = (chapter.content or "").strip()
            if len(body) < 100:
                continue
            character_states = [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "current_realm": c.current_realm or "",
                    "current_location": c.current_location or "",
                    "current_status": c.current_status or "alive",
                }
                for c in project_chars
            ]
            index_dict = {
                "core_events": idx.core_events or [],
                "continuity_notes": idx.continuity_notes or [],
            }
            merged = merge_character_updates_for_debrief([], index_dict, character_states)
            if not merged:
                continue
            for cu in merged:
                if args.dry_run:
                    print(f"  [dry] ch{ch_no} {cu.get('character_name')}: {cu}")
                    continue
                if _apply_cu(db, pid, chapter, cu, project_chars, name_to_rank):
                    applied_total += 1
                    print(
                        f"  ✓ ch{ch_no} {cu.get('character_name')}: "
                        f"realm={cu.get('current_realm')!r} loc={cu.get('current_location')!r}",
                    )
        if args.dry_run:
            print("Dry run — no commit.")
            return
        db.commit()
        print(f"Done. applied={applied_total}")
        for c in project_chars:
            if c.name == "楚惊羽":
                print(f"  楚惊羽 → realm={c.current_realm!r} location={c.current_location!r}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
