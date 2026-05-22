import hashlib
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Chapter, QualityDebt
from app.routers.ai.constants import _QUALITY_DEBT_SEVERITIES, _QUALITY_DEBT_TYPES
from app.routers.ai.text_utils import extract_patch_text, truncate
from app.utils.chapter_numbering import display_chapter_number


def resolve_chapter_for_quality_debt(
    db: Session, project_id: str, debt: QualityDebt
) -> Optional[Chapter]:
    """chapter_id 为空时按 source_chapter_number 回退查找章节。"""
    if debt.chapter_id:
        return (
            db.query(Chapter)
            .filter(Chapter.id == debt.chapter_id, Chapter.project_id == project_id)
            .first()
        )
    for ch in (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id)
        .order_by(Chapter.sort_order, Chapter.created_at)
        .all()
    ):
        if display_chapter_number(ch.title, ch.sort_order) == debt.source_chapter_number:
            return ch
    return None


def quality_debt_fingerprint(project_id: str, chapter_id: str, issue_type: str, summary: str) -> str:
    raw = f"{project_id}|{chapter_id}|{issue_type}|{summary.strip()[:240]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_quality_debt_items(report: dict | None) -> list[dict]:
    if not isinstance(report, dict):
        return []

    candidates: list[dict] = []
    for issue in report.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        issue_type = str(issue.get("type") or "plot").strip().lower()
        severity = str(issue.get("severity") or "medium").strip().lower()
        summary = str(issue.get("description") or issue.get("summary") or "").strip()
        suggested_fix = (
            extract_patch_text(issue.get("suggested_patch"))
            or extract_patch_text(issue.get("suggestion"))
            or extract_patch_text(issue.get("suggested_fix"))
        )
        candidates.append({
            "issue_type": issue_type,
            "severity": severity,
            "summary": summary,
            "suggested_fix": suggested_fix,
        })

    for suggestion in report.get("suggestions") or []:
        if isinstance(suggestion, str):
            text = suggestion.strip()
            if not text:
                continue
            candidates.append({
                "issue_type": "plot",
                "severity": "medium",
                "summary": text,
                "suggested_fix": "",
            })
            continue
        if not isinstance(suggestion, dict):
            continue
        issue_type = str(suggestion.get("type") or "plot").strip().lower()
        severity = str(suggestion.get("severity") or "medium").strip().lower()
        summary = str(suggestion.get("description") or suggestion.get("summary") or suggestion.get("suggestion") or "").strip()
        candidates.append({
            "issue_type": issue_type,
            "severity": severity,
            "summary": summary,
            "suggested_fix": extract_patch_text(suggestion.get("suggested_fix") or suggestion.get("suggestion")),
        })

    debts: list[dict] = []
    seen = set()
    for item in candidates:
        issue_type = item["issue_type"]
        severity = item["severity"]
        summary = item["summary"]
        if not summary:
            continue
        if severity not in _QUALITY_DEBT_SEVERITIES:
            continue
        if issue_type not in _QUALITY_DEBT_TYPES:
            continue
        dedupe_key = (issue_type, summary[:240])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        debts.append({
            **item,
            "severity": severity,
            "summary": truncate(summary, 500),
            "suggested_fix": truncate(item.get("suggested_fix") or "", 500),
        })
    return debts[:8]


def sync_quality_debts(db: Session, project_id: str, chapter: Chapter, report: dict) -> list[QualityDebt]:
    synced: list[QualityDebt] = []
    for item in extract_quality_debt_items(report):
        fingerprint = quality_debt_fingerprint(
            project_id,
            str(chapter.id),
            item["issue_type"],
            item["summary"],
        )
        debt = db.query(QualityDebt).filter(
            QualityDebt.project_id == project_id,
            QualityDebt.fingerprint == fingerprint,
        ).first()
        if debt:
            debt.severity = item["severity"]
            debt.summary = item["summary"]
            debt.suggested_fix = item.get("suggested_fix") or debt.suggested_fix
        else:
            debt = QualityDebt(
                project_id=project_id,
                chapter_id=chapter.id,
                source_chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
                issue_type=item["issue_type"],
                severity=item["severity"],
                status="pending",
                summary=item["summary"],
                suggested_fix=item.get("suggested_fix") or None,
                fingerprint=fingerprint,
            )
            db.add(debt)
        synced.append(debt)
    return synced


def build_quality_debt_context(debts: list[QualityDebt]) -> str:
    pending = [d for d in debts if getattr(d, "status", "pending") == "pending"]
    if not pending:
        return ""
    lines = ["【未解决质量债务 / 必须修正或规避】"]
    for debt in pending[:8]:
        line = (
            f"- 第{debt.source_chapter_number}章 "
            f"[{debt.severity}/{debt.issue_type}] {debt.summary}"
        )
        if debt.suggested_fix:
            line += f"；修正方向：{debt.suggested_fix}"
        lines.append(line)
    return "\n".join(lines)


def pending_quality_debts_for_chapter(
    db: Session,
    project_id: str,
    chapter: Chapter,
    limit: int = 8,
) -> list[QualityDebt]:
    return (
        db.query(QualityDebt)
        .filter(
            QualityDebt.project_id == project_id,
            QualityDebt.status == "pending",
            QualityDebt.source_chapter_number <= display_chapter_number(chapter.title, chapter.sort_order),
        )
        .order_by(QualityDebt.source_chapter_number.desc(), QualityDebt.created_at.desc())
        .limit(limit)
        .all()
    )
