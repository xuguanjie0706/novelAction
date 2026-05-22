"""章节正文局部摘录替换写回（质检/质量债务共用）。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Chapter, ChapterVersion
from app.routers.chapters import count_words
from app.utils.chapter_manuscript import (
    html_to_plain_for_revision,
    plain_text_blocks_to_html,
    split_plain_manuscript_and_index_block,
)


def apply_micro_patch_to_chapter(
    db: Session,
    chapter: Chapter,
    *,
    original_excerpt: str,
    replacement_excerpt: str,
    snapshot_tag: str,
    version_note: str = "局部微调前自动备份",
) -> Chapter:
    """
    在整章叙事纯文本上校验 ``original_excerpt`` 唯一出现后替换，再写回段落 HTML。

    Raises:
        ValueError: 正文为空、摘录未找到或出现多次。
    """
    plain = html_to_plain_for_revision(chapter.content)
    body, index_block = split_plain_manuscript_and_index_block(plain)
    if not (body or "").strip():
        raise ValueError("章节叙事正文为空，无法进行局部微调")

    orig = (original_excerpt or "").strip()
    repl = (replacement_excerpt or "").strip()
    if not orig or not repl:
        raise ValueError("摘录或替换文为空")

    count = body.count(orig)
    if count == 0:
        raise ValueError("摘录在正文中未找到")
    if count > 1:
        raise ValueError(f"摘录在正文中出现 {count} 次，无法安全自动替换")

    new_body = body.replace(orig, repl, 1)
    new_plain = new_body + (f"\n\n{index_block}" if index_block else "")
    new_html = plain_text_blocks_to_html(new_plain)

    snap_tail = f"\n\n--- {snapshot_tag} ---\n{orig}\n=>\n{repl}\n"
    prev_snap = (chapter.manuscript_raw_snapshot or "").strip()
    chapter.manuscript_raw_snapshot = (
        (prev_snap + snap_tail).strip() if prev_snap else snap_tail.strip()
    )[:200000]

    try:
        if (chapter.content or "").strip():
            snap_wc = count_words(chapter.content or "")
            db.add(
                ChapterVersion(
                    chapter_id=chapter.id,
                    content=chapter.content,
                    word_count=snap_wc,
                    note=version_note,
                    is_auto=True,
                )
            )
            db.flush()
    except Exception:
        pass

    chapter.content = new_html
    chapter.word_count = count_words(new_html)
    db.commit()
    db.refresh(chapter)
    return chapter
