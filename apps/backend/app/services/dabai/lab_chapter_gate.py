"""dabai 实验书架：章级写前门控（顺序生成约束）。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline


def dabai_chapter_generate_block_reason(
    db: Session,
    project_id,
    chapter: DabaiChapterOutline,
) -> str | None:
    """首写本章时若上一章无正文则阻断；已有正文的重写不受限。

    Returns:
        阻断原因文案；None 表示允许生成。
    """
    if (chapter.content or "").strip():
        return None
    num = chapter.chapter_number or 0
    if num <= 1:
        return None
    prev = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project_id,
            DabaiChapterOutline.chapter_number == num - 1,
        )
        .first()
    )
    if not prev:
        return f"第{num - 1}章不存在，请先展开章纲"
    if not (prev.content or "").strip():
        title = (prev.title or "").strip()
        suffix = f"《{title}》" if title else ""
        return f"请先生成第{num - 1}章{suffix}正文，再生成第{num}章"
    return None
