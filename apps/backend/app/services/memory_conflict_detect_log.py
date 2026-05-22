"""记忆冲突检测运行日志：落库与查询。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.llm_call_log import LlmCallLog
from app.models.memory_conflict_detect_log import MemoryConflictDetectLog


def _resolve_latest_llm_call_id(db: Session, project_id: str) -> Optional[str]:
    """匹配本项目最近一次 memory_conflict_detect 的 LLM 调用记录。"""
    rows = (
        db.query(LlmCallLog.id, LlmCallLog.context)
        .order_by(LlmCallLog.created_at.desc())
        .limit(30)
        .all()
    )
    pid = str(project_id)
    for log_id, ctx in rows:
        if not isinstance(ctx, dict):
            continue
        if ctx.get("operation") != "memory_conflict_detect":
            continue
        if str(ctx.get("project_id") or "") == pid:
            return str(log_id)
    return None


def persist_memory_conflict_detect_log(
    db: Session,
    *,
    project_id: str | UUID,
    trigger: str,
    status: str,
    duration_ms: int,
    total_chunks_scanned: int,
    conflict_count: int,
    chapter_id: str | UUID | None = None,
    llm_call_log_id: str | UUID | None = None,
    error: str | None = None,
    report: Optional[Dict[str, Any]] = None,
) -> MemoryConflictDetectLog:
    """写入一条检测运行日志并 commit。"""
    llm_id = None
    if llm_call_log_id:
        try:
            llm_id = UUID(str(llm_call_log_id))
        except (ValueError, TypeError):
            llm_id = None
    elif status == "ok" and total_chunks_scanned > 0:
        linked = _resolve_latest_llm_call_id(db, str(project_id))
        if linked:
            try:
                llm_id = UUID(linked)
            except (ValueError, TypeError):
                llm_id = None

    ch_id = None
    if chapter_id:
        try:
            ch_id = UUID(str(chapter_id))
        except (ValueError, TypeError):
            ch_id = None

    output: Dict[str, Any] = {}
    if report:
        output["report"] = {
            "detected_at": report.get("detected_at"),
            "conflicts": report.get("conflicts", [])[:20],
            "conflict_count": len(report.get("conflicts") or []),
        }
        if report.get("error"):
            output["report_error"] = str(report["error"])[:500]

    row = MemoryConflictDetectLog(
        project_id=UUID(str(project_id)),
        chapter_id=ch_id,
        trigger=(trigger or "manual")[:40],
        status=status[:30],
        duration_ms=max(0, int(duration_ms)),
        total_chunks_scanned=max(0, int(total_chunks_scanned)),
        conflict_count=max(0, int(conflict_count)),
        llm_call_log_id=llm_id,
        error=(error[:4000] if error else None),
        output_payload=output,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_memory_conflict_detect_logs(
    db: Session,
    *,
    limit: int = 200,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    project_id: Optional[UUID] = None,
    trigger: Optional[str] = None,
    status: Optional[str] = None,
) -> List[MemoryConflictDetectLog]:
    q = db.query(MemoryConflictDetectLog)
    if since is not None:
        q = q.filter(MemoryConflictDetectLog.created_at >= since)
    if until is not None:
        q = q.filter(MemoryConflictDetectLog.created_at <= until)
    if project_id is not None:
        q = q.filter(MemoryConflictDetectLog.project_id == project_id)
    if trigger and trigger.strip():
        q = q.filter(MemoryConflictDetectLog.trigger == trigger.strip())
    if status and status.strip():
        q = q.filter(MemoryConflictDetectLog.status == status.strip())
    return (
        q.order_by(MemoryConflictDetectLog.created_at.desc())
        .limit(max(1, min(limit, 1000)))
        .all()
    )
