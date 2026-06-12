"""dabai 实验书架质检报告查询 — 管理后台历史回归。"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiQualityReport


def _row_to_dict(row: DabaiQualityReport, *, include_report: bool = True) -> dict[str, Any]:
    rep = row.report or {}
    llm = rep.get("llm") if isinstance(rep.get("llm"), dict) else {}
    snap = rep.get("continuity_snapshot") if isinstance(rep.get("continuity_snapshot"), dict) else {}
    out: dict[str, Any] = {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "chapter_id": str(row.chapter_id),
        "chapter_number": row.chapter_number,
        "source": row.source or "manual",
        "status": row.status,
        "overall_score": row.overall_score,
        "content_word_count": row.content_word_count,
        "content_head_preview": row.content_head_preview or "",
        "continuity_score": llm.get("continuity_score"),
        "continuity_issue": llm.get("continuity_issue") or "",
        "opening_continues_prev_tail": snap.get("opening_continues_prev_tail"),
        "location_bridge_needed": snap.get("location_bridge_needed"),
        "prev_outline_location": snap.get("prev_outline_location"),
        "curr_outline_location": snap.get("curr_outline_location"),
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
    if include_report:
        out["report"] = rep
    return out


def list_dabai_quality_reports(
    db: Session,
    *,
    limit: int = 200,
    since: datetime | None = None,
    until: datetime | None = None,
    project_id: UUID | None = None,
    chapter_id: UUID | None = None,
    chapter_number: int | None = None,
    include_report: bool = False,
) -> list[dict[str, Any]]:
    """分页列出质检历史（默认不含完整 report JSON，详情接口再拉）。"""
    q = db.query(DabaiQualityReport)
    if project_id is not None:
        q = q.filter(DabaiQualityReport.project_id == project_id)
    if chapter_id is not None:
        q = q.filter(DabaiQualityReport.chapter_id == chapter_id)
    if chapter_number is not None:
        q = q.filter(DabaiQualityReport.chapter_number == chapter_number)
    if since is not None:
        q = q.filter(DabaiQualityReport.created_at >= since)
    if until is not None:
        q = q.filter(DabaiQualityReport.created_at <= until)
    rows = (
        q.order_by(DabaiQualityReport.created_at.desc())
        .limit(max(1, min(limit, 1000)))
        .all()
    )
    return [_row_to_dict(r, include_report=include_report) for r in rows]


def list_dabai_quality_debts(
    db: Session, project_id: UUID, *, threshold: int = 70,
) -> list[dict[str, Any]]:
    """质量欠债：各章**最新**报告低于阈值或被阻断的章节清单（派生视图，不另建表）。

    报告表为追加写，按 chapter_id 去重只看最新一条；
    返回按章号升序，供前端欠债面板与重写入口消费。
    """
    rows = (
        db.query(DabaiQualityReport)
        .filter(DabaiQualityReport.project_id == project_id)
        .order_by(DabaiQualityReport.created_at.desc())
        .limit(500)
        .all()
    )
    latest: dict[str, DabaiQualityReport] = {}
    for r in rows:
        latest.setdefault(str(r.chapter_id), r)
    debts = [
        r for r in latest.values()
        if (r.overall_score or 0) < threshold or r.status == "blocked"
    ]
    return [
        _row_to_dict(r, include_report=False)
        for r in sorted(debts, key=lambda r: r.chapter_number or 0)
    ]


def get_dabai_quality_report(db: Session, report_id: UUID) -> dict[str, Any] | None:
    row = db.query(DabaiQualityReport).filter(DabaiQualityReport.id == report_id).first()
    if not row:
        return None
    data = _row_to_dict(row, include_report=True)
    project = db.query(DabaiProject).filter(DabaiProject.id == row.project_id).first()
    ch = db.query(DabaiChapterOutline).filter(DabaiChapterOutline.id == row.chapter_id).first()
    data["project_title"] = (project.title or project.logline or "") if project else ""
    data["chapter_title"] = (ch.title or "") if ch else ""
    return data
