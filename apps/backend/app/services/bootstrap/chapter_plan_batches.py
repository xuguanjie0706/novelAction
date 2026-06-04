"""章纲展开批次：整卷单次优先，超 token 预算时按 30 章切块 + 余数。"""
from __future__ import annotations

from typing import Any

# 实测：30 章 × 15 字段 JSON ≈ 16k completion tokens
EST_COMPLETION_TOKENS_PER_CHAPTER = 520

MIN_VOLUME_PLANNED_CHAPTERS = 15
MAX_VOLUME_PLANNED_CHAPTERS = 80
DEFAULT_VOLUME_PLANNED_CHAPTERS = 30
BATCH_CHUNK_SIZE = 30


def normalize_volume_planned_chapters(value: object, *, default: int = DEFAULT_VOLUME_PLANNED_CHAPTERS) -> int:
    """与 Bootstrap Step 9 落库区间对齐：15–80，非法值回退 default。"""
    try:
        planned = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if planned < MIN_VOLUME_PLANNED_CHAPTERS:
        return default
    if planned > MAX_VOLUME_PLANNED_CHAPTERS:
        return MAX_VOLUME_PLANNED_CHAPTERS
    return planned


def chapter_plan_batch_ranges(planned: int, max_completion_tokens: int) -> list[tuple[int, int]]:
    """按输出 token 预算切批；单批硬上限 30 章，避免超大 JSON 解析失败。"""
    if planned <= 0:
        return []
    token_cap = max(
        BATCH_CHUNK_SIZE,
        max_completion_tokens // EST_COMPLETION_TOKENS_PER_CHAPTER,
    )
    # 实测 50 章整批一次生成易出 JSON 笔误（尾部 ]]、字段内引号等）；30 章一批更稳。
    max_in_one_shot = min(token_cap, BATCH_CHUNK_SIZE)
    if planned <= max_in_one_shot:
        return [(1, planned)]
    ranges: list[tuple[int, int]] = []
    start = 1
    while start <= planned:
        end = min(start + BATCH_CHUNK_SIZE - 1, planned)
        ranges.append((start, end))
        start = end + 1
    return ranges


def log_chapter_plan_batches(
    logger: Any,
    *,
    tag: str,
    planned: int,
    ranges: list[tuple[int, int]],
    max_completion_tokens: int,
) -> None:
    """记录整卷单次或分批策略（vol_chapters / vol1_chapters 共用）。"""
    if len(ranges) == 1:
        logger.info(
            "%s 整卷单次生成：%d 章，max_tokens=%d",
            tag,
            planned,
            max_completion_tokens,
        )
    else:
        logger.info(
            "%s 分批生成：%d 批 %s，max_tokens=%d/批",
            tag,
            len(ranges),
            ranges,
            max_completion_tokens,
        )
