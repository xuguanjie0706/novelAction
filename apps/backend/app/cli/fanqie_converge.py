"""
存量番茄项目归一化：卷纲 / 境界表；可选清除已物化章纲以便重新按需展开。

用法:
  cd apps/backend && python -m app.cli.fanqie_converge <project_id>
  cd apps/backend && python -m app.cli.fanqie_converge <project_id> --strip-chapter-plans
  cd apps/backend && python -m app.cli.fanqie_converge <project_id> --gen-volumes
"""
from __future__ import annotations

import sys

from app.database import SessionLocal
from app.services.bootstrap.fanqie_normalize import backfill_fanqie_project


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if not args else 0)
    project_id = args[0].strip()
    flags = set(args[1:])
    strip = "--strip-chapter-plans" in flags
    gen_volumes = "--gen-volumes" in flags
    db = SessionLocal()
    try:
        if gen_volumes:
            from app.services.bootstrap.fanqie_gen_volumes import regenerate_fanqie_volumes_sync

            n = regenerate_fanqie_volumes_sync(db, project_id)
            print(f"OK: volume outlines for {project_id} — {n} volume(s) in DB")
        backfill_fanqie_project(db, project_id, strip_chapter_plans=strip)
        msg = f"OK: fanqie converge done for {project_id}"
        if strip:
            msg += " (chapter_plan removed; use 展开章纲 on outline)"
        print(msg)
    finally:
        db.close()


if __name__ == "__main__":
    main()
