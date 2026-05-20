"""SEQ-05 embedding 增强（异步，可选）。"""

from __future__ import annotations

from app.services.outline_linter.helpers import ChapterSnapshot
from app.services.outline_linter.schemas import LinterIssue


def snapshots_to_chapter_dicts(chapters: list[ChapterSnapshot]) -> list[dict]:
    return [
        {
            "number": ch.chapter_number,
            "title": ch.title,
            "core_event": ch.summary or "",
            "character_change": ch.conflict or "",
            "end_hook": ch.end_hook_text(),
            "opening_hook": ch.hook or "",
            "foreshadow": ch.ex_str("foreshadow"),
        }
        for ch in chapters
    ]


async def lint_embedding_duplicates_async(
    chapters: list[ChapterSnapshot],
    *,
    scope: str = "volume",
) -> list[LinterIssue]:
    """调用 embedding 服务做软重复检测；失败时返回空列表。"""
    from app.routers.outline.helpers.embedding_dup import (
        analyze_outline_embedding_duplicates,
    )

    dicts = snapshots_to_chapter_dicts(chapters)
    if len(dicts) < 2:
        return []

    try:
        report = await analyze_outline_embedding_duplicates(dicts, scope=scope)
    except Exception:
        return []

    issues: list[LinterIssue] = []
    for raw in report.get("issues") or []:
        if not isinstance(raw, dict):
            continue
        numbers = raw.get("chapter_numbers") or []
        ch_num = numbers[-1] if numbers else None
        issues.append(LinterIssue(
            rule_id="SEQ-05E",
            severity=str(raw.get("severity", "high")),
            scope="sequence",
            message=str(raw.get("description", "embedding 语义重复")),
            suggestion="拉开两章核心事件与章末钩子差异",
            chapter_number_in_volume=ch_num if isinstance(ch_num, int) else None,
        ))
    return issues
