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

# --------------------------------------------------------------------------
# target_words 驱动的推算函数（单一数据源）
# --------------------------------------------------------------------------

def words_to_plan(target_words: int) -> dict:
    """从目标字数推算章数、卷数。

    返回:
        total_chapters: 总章数
        total_volumes:  建议卷数
        chapters_last:  最后一卷章数（可能 < 60）
        scale_label:    对应的规模标签（仅用于 UI 显示，不参与计算）
    """
    tw = max(int(target_words or 1_200_000), MIN_CHAPTERS_PER_VOLUME * TARGET_WORDS_PER_CHAPTER)
    total_chapters = round(tw / TARGET_WORDS_PER_CHAPTER)
    full_volumes, remainder = divmod(total_chapters, TARGET_CHAPTERS_PER_VOLUME)
    # 余数不足半卷（30章）时并入前一卷；否则独立成卷
    if remainder == 0:
        total_volumes = full_volumes
        chapters_last = TARGET_CHAPTERS_PER_VOLUME
    elif remainder < MIN_CHAPTERS_PER_VOLUME:
        total_volumes = max(1, full_volumes)
        chapters_last = TARGET_CHAPTERS_PER_VOLUME + remainder  # 最后一卷略超 60，后续 split 会拆
    else:
        total_volumes = full_volumes + 1
        chapters_last = remainder

    # 推断标签（仅显示用）
    if tw <= 500_000:
        scale_label = "micro"
    elif tw <= 900_000:
        scale_label = "short"
    elif tw <= 1_400_000:
        scale_label = "medium"
    elif tw <= 1_700_000:
        scale_label = "long"
    else:
        scale_label = "epic"

    return {
        "total_chapters": total_chapters,
        "total_volumes": total_volumes,
        "chapters_last": chapters_last,
        "scale_label": scale_label,
    }


def target_total_chapters_from_words(target_words: int) -> int:
    """直接返回总章数下限（用于 normalize_volume_plan）。"""
    return words_to_plan(target_words)["total_chapters"]


def target_total_chapters(scale_hint: str) -> int:
    """兼容旧调用：通过 scale_hint 查表。"""
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


def normalize_volume_plan(
    volumes: list[dict],
    scale_hint: str = "auto",
    target_words: int | None = None,
) -> list[dict]:
    """标准化卷规划。

    优先使用 target_words 计算总章数下限；
    若未提供则回退到 scale_hint 查表（向后兼容）。
    """
    normalized = [
        {**vol, "planned_chapters": normalize_chapter_count(vol.get("planned_chapters"))}
        for vol in volumes
    ]
    if not normalized:
        return normalized

    if target_words:
        minimum_total = target_total_chapters_from_words(target_words)
    else:
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
