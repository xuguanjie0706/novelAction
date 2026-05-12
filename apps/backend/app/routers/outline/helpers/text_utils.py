"""大纲文本清洗与玄幻题材科幻词替换。"""
from __future__ import annotations

from app.services.xuanhuan_lexicon import (
    is_xuanhuan_like_genre as _is_xuanhuan_like_genre,
)

def _clean_outline_text(value: object, limit: int = 120) -> str:
    return " ".join(str(value or "").split())[:limit]


def _sanitize_xuanhuan_outline_text(text: str) -> str:
    cleaned = text
    replacements = [
        ("首席工程师", "大阵主祭"),
        ("AI化", "傀儡化"),
        ("人工智能", "灵智禁制"),
        ("AI", "灵智"),
        ("半机械", "半傀"),
        ("机械", "机关"),
        ("芯片", "命纹碎片"),
        ("量子", "微尘"),
        ("基因实验室", "血脉禁室"),
        ("星际文明", "诸天古域"),
        ("星际", "诸天"),
        ("程序上传", "神识刻印"),
        ("控制台", "阵枢石台"),
    ]
    for src, dst in replacements:
        cleaned = cleaned.replace(src, dst)
    return cleaned


def _sanitize_generated_outline_chapter(chapter: dict, genre: str | None) -> dict:
    if not _is_xuanhuan_like_genre(genre):
        return chapter
    sanitized = dict(chapter)
    for field in ("title", "opening_hook", "core_event", "character_change", "foreshadow", "end_hook"):
        value = sanitized.get(field)
        if isinstance(value, str) and value:
            sanitized[field] = _sanitize_xuanhuan_outline_text(value)
    return sanitized

