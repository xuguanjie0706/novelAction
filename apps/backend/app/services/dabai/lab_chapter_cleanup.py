"""dabai 实验书架 — 清空单章写作产物（正文 + 预警/分场/质检/记忆/台账派生）。

章纲五拍保留，仅删除「写作期生成」内容，便于按章纲重写而不污染后续 canon。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import (
    DabaiAsset,
    DabaiClue,
    DabaiMemory,
    DabaiPanelSnapshot,
    DabaiPreWarnRecord,
    DabaiQualityReport,
    DabaiRelation,
    DabaiScenePlan,
)


@dataclass
class ChapterWritingClearResult:
    """清章结果摘要（供 API 与测试断言）。"""

    chapter_id: str
    chapter_number: int
    had_content: bool
    counts: dict[str, int] = field(default_factory=dict)


def later_chapters_have_content(
    db: Session, project_id: UUID, before_chapter: int,
) -> bool:
    """后续章是否已有正文（须先清后续章，避免记忆/衔接链断裂）。"""
    row = (
        db.query(DabaiChapterOutline.id)
        .filter(
            DabaiChapterOutline.project_id == project_id,
            DabaiChapterOutline.chapter_number > before_chapter,
            DabaiChapterOutline.content.isnot(None),
            DabaiChapterOutline.content != "",
        )
        .first()
    )
    return row is not None


def _delete_by_chapter_id(db: Session, model, project_id: UUID, chapter_id: UUID) -> int:
    return (
        db.query(model)
        .filter(model.project_id == project_id, model.chapter_id == chapter_id)
        .delete(synchronize_session=False)
    )


def _revert_ledger_for_chapter(
    db: Session, project: DabaiProject, chapter_number: int,
) -> dict[str, int]:
    """撤销本章复盘对资产/关系/线索的写入。不 commit。"""
    stats = {"assets_removed": 0, "assets_reverted": 0, "relations_reverted": 0,
             "clues_planted": 0, "clues_reopened": 0}

    stats["assets_removed"] = (
        db.query(DabaiAsset)
        .filter(
            DabaiAsset.project_id == project.id,
            DabaiAsset.source == "debrief",
            DabaiAsset.acquired_chapter == chapter_number,
        )
        .delete(synchronize_session=False)
    )

    for row in (
        db.query(DabaiAsset)
        .filter(
            DabaiAsset.project_id == project.id,
            DabaiAsset.status_chapter == chapter_number,
        )
        .all()
    ):
        if row.source != "debrief" and row.acquired_chapter != chapter_number:
            continue
        if row.status in ("consumed", "lost"):
            row.status = "active"
            row.status_chapter = row.acquired_chapter
            stats["assets_reverted"] += 1
        elif row.status == "active" and (row.enhancement_level or 0) > 0:
            row.enhancement_level = max(0, (row.enhancement_level or 0) - 1)
            stats["assets_reverted"] += 1

    for row in (
        db.query(DabaiAsset)
        .filter(
            DabaiAsset.project_id == project.id,
            DabaiAsset.last_used_chapter == chapter_number,
        )
        .all()
    ):
        row.last_used_chapter = None
        stats["assets_reverted"] += 1

    for row in db.query(DabaiRelation).filter(DabaiRelation.project_id == project.id).all():
        history = list(row.history or [])
        trimmed = [h for h in history if h.get("chapter") != chapter_number]
        if len(trimmed) == len(history):
            continue
        if not trimmed:
            if row.source == "debrief":
                db.delete(row)
                stats["relations_reverted"] += 1
            continue
        row.history = trimmed
        last = trimmed[-1]
        row.attitude = str(last.get("attitude") or row.attitude or "")[:40]
        try:
            row.last_change_chapter = int(last.get("chapter"))
        except (TypeError, ValueError):
            row.last_change_chapter = None
        stats["relations_reverted"] += 1

    stats["clues_planted"] = (
        db.query(DabaiClue)
        .filter(
            DabaiClue.project_id == project.id,
            DabaiClue.chapter_planted == chapter_number,
            DabaiClue.source == "debrief",
        )
        .delete(synchronize_session=False)
    )

    for clue in (
        db.query(DabaiClue)
        .filter(
            DabaiClue.project_id == project.id,
            DabaiClue.chapter_resolved == chapter_number,
        )
        .all()
    ):
        clue.chapter_resolved = None
        if clue.status == "resolved":
            clue.status = "open"
        stats["clues_reopened"] += 1

    return stats


def _sync_meta_from_panel(db: Session, project: DabaiProject, chapter_number: int) -> None:
    """清章后把 meta.protagonist_realm 回退到剩余最新面板快照。"""
    prev = (
        db.query(DabaiPanelSnapshot)
        .filter(
            DabaiPanelSnapshot.project_id == project.id,
            DabaiPanelSnapshot.chapter_number < chapter_number,
        )
        .order_by(DabaiPanelSnapshot.chapter_number.desc())
        .first()
    )
    meta = dict(project.meta or {})
    if prev and isinstance(prev.snapshot, dict):
        from app.services.dabai.lab_realm_baseline import _label_from_snapshot

        realm = _label_from_snapshot(prev.snapshot, project).strip()
        if realm:
            meta["protagonist_realm"] = realm
            meta["protagonist_realm_chapter"] = prev.chapter_number
        elif meta.get("protagonist_realm_chapter") == chapter_number:
            meta.pop("protagonist_realm", None)
            meta.pop("protagonist_realm_chapter", None)
    elif meta.get("protagonist_realm_chapter") == chapter_number:
        meta.pop("protagonist_realm", None)
        meta.pop("protagonist_realm_chapter", None)
    project.meta = meta


def _reset_outline_realm_rank(db: Session, ch: DabaiChapterOutline) -> None:
    """清章后 realm_rank 回退到上一章章纲值（bootstrap 规划）。"""
    num = ch.chapter_number or 1
    if num <= 1:
        return
    prev = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == ch.project_id,
            DabaiChapterOutline.chapter_number == num - 1,
        )
        .first()
    )
    if prev and prev.realm_rank is not None:
        ch.realm_rank = prev.realm_rank


def clear_dabai_chapter_writing(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    *,
    allow_with_later_content: bool = False,
) -> ChapterWritingClearResult:
    """清空单章全部写作产物；章纲五拍保留。成功路径内 commit。

    Raises:
        ValueError: 后续章已有正文且未显式允许。
    """
    ch_num = ch.chapter_number or 0
    if not allow_with_later_content and later_chapters_have_content(db, project.id, ch_num):
        raise ValueError("后续章节已有正文，请先清空更高章号的章节")

    had_content = bool((ch.content or "").strip())
    cid = ch.id
    counts: dict[str, int] = {}

    counts["pre_warn"] = _delete_by_chapter_id(db, DabaiPreWarnRecord, project.id, cid)
    counts["scene_plans"] = _delete_by_chapter_id(db, DabaiScenePlan, project.id, cid)
    counts["quality_reports"] = _delete_by_chapter_id(db, DabaiQualityReport, project.id, cid)
    counts["memories"] = _delete_by_chapter_id(db, DabaiMemory, project.id, cid)
    counts["panel_snapshots"] = _delete_by_chapter_id(db, DabaiPanelSnapshot, project.id, cid)

    ledger = _revert_ledger_for_chapter(db, project, ch_num)
    counts.update(ledger)

    _sync_meta_from_panel(db, project, ch_num)
    _reset_outline_realm_rank(db, ch)
    from app.services.dabai.lab_prewarn_outline_lock import sync_cast_realm_from_outline
    sync_cast_realm_from_outline(db, project, ch)

    ch.content = ""
    ch.status = "planned"

    db.commit()
    db.refresh(ch)

    counts["content"] = 1 if had_content else 0
    return ChapterWritingClearResult(
        chapter_id=str(cid),
        chapter_number=ch_num,
        had_content=had_content,
        counts=counts,
    )
