"""质检根因台账 —— 收集层（不调用 LLM）。

职责
----
从一次 ``quality_check`` 报告里提取**所有低分项**（任意维度 score<8，或一条 issue），
归一化后按指纹幂等落库到 ``quality_root_cause_logs``（status=pending），等分析层补根因。

禁止事项：本文件不写业务 prompt、不调用模型；LLM 根因分类在 ``quality_root_cause.py``。
"""

from __future__ import annotations

import hashlib
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Chapter, QualityRootCauseLog

# 维度低分阈值：用户约定「任意一项低于 8 即触发」。
LOW_SCORE_THRESHOLD = 8


def _coerce_score(raw: Any) -> Optional[int]:
    """把维度里的 score 容错为 int；非数值返回 None。"""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return int(round(raw))
    if isinstance(raw, str):
        s = raw.strip()
        try:
            return int(round(float(s)))
        except (ValueError, TypeError):
            return None
    return None


def _severity_from_score(score: Optional[int]) -> str:
    """维度低分按分数推严重度：<6 高 / <7 中 / 其余低。"""
    if score is None:
        return "medium"
    if score < 6:
        return "high"
    if score < 7:
        return "medium"
    return "low"


def extract_low_items(report: dict | None) -> list[dict]:
    """从质检报告提取低分项，归一化为统一结构。

    Args:
        report: ``quality_check`` 返回的报告 dict。

    Returns:
        每项含 ``item_kind`` / ``dimension`` / ``score`` / ``severity`` / ``problem_summary``。
        维度项：score<8 的 dimensions；issue 项：issues 全量（每条都是被标记的问题）。
    """
    if not isinstance(report, dict):
        return []

    items: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    dims = report.get("dimensions")
    if isinstance(dims, dict):
        for key, val in dims.items():
            if not isinstance(val, dict):
                continue
            score = _coerce_score(val.get("score"))
            if score is None or score >= LOW_SCORE_THRESHOLD:
                continue
            comment = str(val.get("comment") or val.get("status") or "").strip()
            dedupe = ("dimension", str(key), comment[:120])
            if dedupe in seen:
                continue
            seen.add(dedupe)
            items.append({
                "item_kind": "dimension",
                "dimension": str(key)[:60],
                "score": score,
                "severity": _severity_from_score(score),
                "problem_summary": comment or f"维度 {key} 评分 {score}（<{LOW_SCORE_THRESHOLD}）",
            })

    for issue in report.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        itype = str(issue.get("type") or "issue").strip().lower()[:60]
        desc = str(issue.get("description") or issue.get("summary") or "").strip()
        if not desc:
            continue
        sev = str(issue.get("severity") or "medium").strip().lower()
        if sev not in ("low", "medium", "high"):
            sev = "medium"
        dedupe = ("issue", itype, desc[:120])
        if dedupe in seen:
            continue
        seen.add(dedupe)
        items.append({
            "item_kind": "issue",
            "dimension": itype,
            "score": None,
            "severity": sev,
            "problem_summary": desc,
        })

    return items[:20]


def root_cause_fingerprint(project_id: str, chapter_id: str, item_kind: str, dimension: str, summary: str) -> str:
    raw = f"{project_id}|{chapter_id}|{item_kind}|{dimension}|{summary.strip()[:200]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def record_low_items(
    db: Session,
    project_id: str,
    chapter: Chapter,
    items: list[dict],
    run_id: str,
) -> list[QualityRootCauseLog]:
    """把低分项按指纹幂等写入台账；已存在则累加 occurrence_count 并复位为 pending。

    复位为 pending 的动机：同一问题再次出现说明上次的根因/修复没生效，需要重新归因。
    """
    saved: list[QualityRootCauseLog] = []
    ch_no = chapter.sort_order or 0
    for item in items:
        summary = item["problem_summary"]
        fp = root_cause_fingerprint(
            str(project_id), str(chapter.id), item["item_kind"], item["dimension"], summary
        )
        row = (
            db.query(QualityRootCauseLog)
            .filter(
                QualityRootCauseLog.project_id == project_id,
                QualityRootCauseLog.chapter_id == chapter.id,
                QualityRootCauseLog.fingerprint == fp,
            )
            .first()
        )
        if row:
            row.occurrence_count = (row.occurrence_count or 1) + 1
            row.run_id = run_id
            row.score = item["score"]
            row.severity = item["severity"]
            row.problem_summary = summary
            row.analysis_status = "pending"
            row.root_cause_category = "pending"
        else:
            row = QualityRootCauseLog(
                project_id=project_id,
                chapter_id=chapter.id,
                source_chapter_number=ch_no,
                run_id=run_id,
                item_kind=item["item_kind"],
                dimension=item["dimension"],
                score=item["score"],
                severity=item["severity"],
                problem_summary=summary,
                root_cause_category="pending",
                analysis_status="pending",
                evidence={},
                fingerprint=fp,
                occurrence_count=1,
            )
            db.add(row)
        saved.append(row)
    db.flush()
    return saved
