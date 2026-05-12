"""章节大纲镜像重复：三字段签名。"""
from __future__ import annotations

from app.routers.outline.helpers.text_utils import _clean_outline_text

def _chapter_duplicate_signature(chapter: dict) -> tuple[str, str, str] | None:
    core_event = _clean_outline_text(chapter.get("core_event"), 240)
    character_change = _clean_outline_text(chapter.get("character_change"), 220)
    end_hook = _clean_outline_text(chapter.get("end_hook"), 220)
    if not core_event or not (character_change or end_hook):
        return None
    return (core_event, character_change, end_hook)
