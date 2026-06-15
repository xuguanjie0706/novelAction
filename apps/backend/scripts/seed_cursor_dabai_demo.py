"""将 Cursor Agent 生成的五章正文写入 dabai 书架（真实 LLM 骨架 + 手工正文）。

注意：mock 已下线，运行前需 export DABAI_BASE_URL / DABAI_API_KEY / DABAI_MODEL。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dabai.config import DabaiConfig  # noqa: E402
from dabai.pipeline import collect_bootstrap, dabai_llm_call  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.dabai import DabaiChapterOutline, DabaiProject  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.dabai_persist import persist_bootstrap_result  # noqa: E402
from scripts.cursor_dabai_demo_chapters import CHAPTERS  # noqa: E402


def main() -> None:
    db = SessionLocal()
    user = db.query(User).order_by(User.created_at.asc()).first()
    if not user:
        raise SystemExit("数据库无用户，请先在创作端登录注册。")

    cfg = DabaiConfig(
        logline="【Cursor演示】废柴林凡觉醒万物吞噬系统，外门逆袭打脸（正文由 Cursor Agent 生成）",
        volume_count=1,
        volume_chapters=5,
    )
    result = asyncio.run(collect_bootstrap(cfg, dabai_llm_call(cfg)))
    project = persist_bootstrap_result(db, result, user.id)

    project.title = f"【Cursor演示】{project.title or '开局吞了退婚书'}"
    project.mock = False  # 正文非 mock，标记为 Agent 演示书
    db.commit()

    chapters = (
        db.query(DabaiChapterOutline)
        .filter(DabaiChapterOutline.project_id == project.id)
        .order_by(DabaiChapterOutline.chapter_number.asc())
        .all()
    )
    for ch in chapters:
        body = CHAPTERS.get(ch.chapter_number)
        if not body:
            continue
        ch.content = body.strip()
        ch.status = "written"

    db.commit()
    db.refresh(project)

    print("OK: dabai demo project created")
    print(f"  user: {user.username or user.email} ({user.id})")
    print(f"  project_id: {project.id}")
    print(f"  title: {project.title}")
    print(f"  chapters_written: {sum(1 for c in chapters if (c.content or '').strip())}")
    print(f"  open: http://localhost:3173/dabai/{project.id}/write-dabailab")
    db.close()


if __name__ == "__main__":
    main()
