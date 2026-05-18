"""Bootstrap 开局承诺 → ReaderPromise 表种子写入（通用 / 番茄共用）。"""

from __future__ import annotations

from typing import Any


def seed_reader_promises(
    svc: Any,
    project: Any,
    entries: list[dict],
    *,
    origin: str,
) -> int:
    """将结构化承诺条目写入 ReaderPromise。

    Args:
        svc: GenerationService 薄壳（需有 db）。
        project: Project ORM。
        entries: 每项含 text / promise_type / source_chapter_number /
            expected_chapter_window / priority / audience_aware / contract_key。
        origin: 写入 extra.origin，便于溯源。

    Returns:
        成功插入条数。
    """
    from app.models import ReaderPromise

    if not entries:
        return 0

    count = 0
    try:
        for m in entries:
            text = m.get("text")
            if not text:
                continue
            if isinstance(text, list):
                text = "；".join(str(t) for t in text if t)
            text = str(text).strip()
            if not text:
                continue
            rp = ReaderPromise(
                project_id=project.id,
                promise_text=text[:500],
                promise_type=m.get("promise_type", "chapter_ending"),
                source_chapter_number=m.get("source_chapter_number"),
                expected_chapter_window=m.get("expected_chapter_window", 3),
                priority=m.get("priority", 3),
                audience_aware=m.get("audience_aware", 3),
                status="open",
                extra={
                    "origin": origin,
                    "contract_key": m.get("contract_key"),
                },
            )
            svc.db.add(rp)
            count += 1
        if count:
            svc.db.commit()
    except Exception:
        pass
    return count
