"""大纲文本清洗与玄幻题材科幻词替换。"""
from __future__ import annotations

from app.services.xuanhuan_lexicon import (
    is_xuanhuan_like_genre as _is_xuanhuan_like_genre,
    sanitize_outline_chapter as _sanitize_outline_chapter,
    sanitize_xuanhuan_text as _sanitize_xuanhuan_text,
)


def _clean_outline_text(value: object, limit: int = 120) -> str:
    return " ".join(str(value or "").split())[:limit]


def _sanitize_xuanhuan_outline_text(text: str) -> str:
    return _sanitize_xuanhuan_text(text)


def _sanitize_generated_outline_chapter(chapter: dict, genre: str | None) -> dict:
    return _sanitize_outline_chapter(chapter, genre)
