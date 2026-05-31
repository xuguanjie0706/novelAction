"""大纲问题台账落库与高频统计。

职责：把一次质检的 IssueSet 幂等写入 outline_issue_logs（同指纹累加 occurrence_count），
并提供「高频问题」查询，供生成期回灌使用。
约束：只做 DB 读写，不直连 LLM；保持 <150 行。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models import OutlineIssueLog
from app.services.outline_quality.contract import Issue, IssueSet

# severity 字典序 max 会把 medium 误判为比 critical 更严重，用 rank 取 min（最严重）。
_SEV_RANK_ISSUE = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _worse_severity(a: str, b: str) -> str:
    return a if _SEV_RANK_ISSUE.get(a, 9) <= _SEV_RANK_ISSUE.get(b, 9) else b


def _apply_issue_to_row(row: OutlineIssueLog, issue: Issue) -> None:
    """把单条 Issue 合并进台账行（累加次数、保留更严重级别）。"""
    row.occurrence_count = (row.occurrence_count or 1) + 1
    row.severity = _worse_severity(row.severity or "medium", issue.severity)
    row.message = issue.message
    if issue.suggestion:
        row.suggestion = issue.suggestion


# severity 字典序 max 会把 medium 误判为比 critical 更严重，用 rank 取 min（最严重）。
_SEV_RANK = case(
    (OutlineIssueLog.severity == "critical", 0),
    (OutlineIssueLog.severity == "high", 1),
    (OutlineIssueLog.severity == "medium", 2),
    (OutlineIssueLog.severity == "low", 3),
    else_=9,
)
_RANK_TO_SEV = {0: "critical", 1: "high", 2: "medium", 3: "low"}


def record_issue_set(
    db: Session,
    project_id: Any,
    issue_set: IssueSet,
    *,
    commit: bool = True,
) -> int:
    """把 IssueSet 幂等写入台账。

    同 (project, volume, fingerprint) 已存在则更新 severity/message 并累加 occurrence_count，
    否则插入新行。返回本次处理的问题条数。
    """
    if not issue_set.issues:
        return 0

    volume_node_id = issue_set.volume_node_id
    # 同一次 flush 前 session 内未落库的新行，query 查不到；用 dict 避免重复 INSERT。
    pending_by_fp: dict[str, OutlineIssueLog] = {}
    processed = 0
    for issue in issue_set.issues:
        fp = issue.fingerprint
        existing = pending_by_fp.get(fp)
        if existing is None:
            existing = (
                db.query(OutlineIssueLog)
                .filter(
                    OutlineIssueLog.project_id == project_id,
                    OutlineIssueLog.volume_node_id == volume_node_id,
                    OutlineIssueLog.fingerprint == fp,
                )
                .first()
            )
        if existing is not None:
            _apply_issue_to_row(existing, issue)
        else:
            row = OutlineIssueLog(
                project_id=project_id,
                volume_node_id=volume_node_id,
                rule_id=issue.rule_id,
                dimension=issue.dimension,
                severity=issue.severity,
                source=issue.source,
                field=issue.field or None,
                chapter_number=issue.chapter_number,
                message=issue.message,
                suggestion=issue.suggestion or None,
                fingerprint=fp,
                occurrence_count=1,
            )
            db.add(row)
            pending_by_fp[fp] = row
        processed += 1

    if commit:
        db.commit()
    else:
        db.flush()
    return processed


def top_frequent_issues(
    db: Session,
    project_id: Any,
    *,
    limit: int = 8,
    min_severity: str | None = "high",
    exclude_volume_node_id: Any = None,
) -> list[dict[str, Any]]:
    """按规则聚合返回高频问题（跨卷），用于生成期回灌。

    Args:
        min_severity: 仅统计 >= 该严重度的问题；None 表示不过滤。
        exclude_volume_node_id: 排除当前正在生成的卷，避免自我回灌。
    """
    severity_floor = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    allowed: set[str] | None = None
    if min_severity:
        floor = severity_floor.get(min_severity, 1)
        allowed = {s for s, v in severity_floor.items() if v <= floor}

    q = (
        db.query(
            OutlineIssueLog.rule_id,
            OutlineIssueLog.dimension,
            func.sum(OutlineIssueLog.occurrence_count).label("total"),
            func.min(_SEV_RANK).label("severity_rank"),
            func.max(OutlineIssueLog.suggestion).label("suggestion"),
            func.max(OutlineIssueLog.field).label("field"),
        )
        .filter(OutlineIssueLog.project_id == project_id)
    )
    if allowed is not None:
        q = q.filter(OutlineIssueLog.severity.in_(allowed))
    if exclude_volume_node_id is not None:
        q = q.filter(OutlineIssueLog.volume_node_id != exclude_volume_node_id)

    rows = (
        q.group_by(OutlineIssueLog.rule_id, OutlineIssueLog.dimension)
        .order_by(func.sum(OutlineIssueLog.occurrence_count).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "rule_id": r.rule_id,
            "dimension": r.dimension,
            "count": int(r.total or 0),
            "severity": _RANK_TO_SEV.get(int(r.severity_rank), "medium"),
            "suggestion": r.suggestion or "",
            "field": r.field or "",
        }
        for r in rows
    ]
