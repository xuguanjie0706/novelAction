from __future__ import annotations

import math
from typing import Iterable, Sequence, TypeVar


MIN_CHAPTERS_PER_VOLUME = 30
TARGET_CHAPTERS_PER_VOLUME = 60
TARGET_WORDS_PER_CHAPTER = 2300
WORD_ESTIMATE_RANGE = (2200, 2400)

# 总章数下限；字数按每章 TARGET_WORDS_PER_CHAPTER（2300）估算（与 ai_service 文案一致）
SCALE_TARGET_TOTAL_CHAPTERS = {
    "micro": 180,   # 约 41 万字 → 超短篇目标约 40 万字
    "auto": 540,
    "short": 360,
    "medium": 540,
    "long": 660,
    "epic": 870,    # 约 200 万字
}

T = TypeVar("T")


def target_total_chapters(scale_hint: str) -> int:
    return SCALE_TARGET_TOTAL_CHAPTERS.get(scale_hint, SCALE_TARGET_TOTAL_CHAPTERS["auto"])


def normalize_chapter_count(value: object, minimum: int = MIN_CHAPTERS_PER_VOLUME) -> int:
    if not isinstance(value, int) or value < 1:
        return minimum
    rounded_units = math.floor(value / MIN_CHAPTERS_PER_VOLUME + 0.5)
    return max(minimum, rounded_units * MIN_CHAPTERS_PER_VOLUME)


def _split_volume(vol: dict) -> list[dict]:
    planned = normalize_chapter_count(vol.get("planned_chapters"))
    chunks: list[int] = []
    remaining = planned
    while remaining > 0:
        chunk = min(TARGET_CHAPTERS_PER_VOLUME, remaining)
        chunks.append(chunk)
        remaining -= chunk

    if len(chunks) == 1:
        return [{**vol, "planned_chapters": chunks[0]}]

    title = str(vol.get("title") or "未命名卷")
    numerals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    return [
        {
            **vol,
            "title": f"{title}（{numerals[idx] if idx < len(numerals) else idx + 1}）",
            "planned_chapters": chunk,
        }
        for idx, chunk in enumerate(chunks)
    ]


def normalize_volume_plan(volumes: list[dict], scale_hint: str) -> list[dict]:
    normalized = [
        {**vol, "planned_chapters": normalize_chapter_count(vol.get("planned_chapters"))}
        for vol in volumes
    ]
    if not normalized:
        return normalized

    minimum_total = target_total_chapters(scale_hint)
    current_total = sum(vol["planned_chapters"] for vol in normalized)
    if current_total < minimum_total:
        missing = minimum_total - current_total
        extra = math.ceil(missing / MIN_CHAPTERS_PER_VOLUME) * MIN_CHAPTERS_PER_VOLUME
        last = normalized[-1]
        normalized[-1] = {
            **last,
            "planned_chapters": last["planned_chapters"] + extra,
        }

    split: list[dict] = []
    for vol in normalized:
        split.extend(_split_volume(vol))
    return split


def chunk_by_volume(items: Sequence[T], size: int = TARGET_CHAPTERS_PER_VOLUME) -> Iterable[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
