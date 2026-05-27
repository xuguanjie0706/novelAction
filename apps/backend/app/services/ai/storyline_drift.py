"""
storyline_drift.py — 故事线织网复盘回填、漂移检测与 QualityDebt 落库。

复盘提交后：写入 StoryLine.extra.actual_beats、更新 Project.extra.storyline_drift_corrections，
供下一章 weave_engine 前馈补偿。
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import Chapter, OutlineNode, Project, QualityDebt, StoryLine
from app.routers.ai.quality_debt import quality_debt_fingerprint
from app.services.ai.storyline_weave_engine import _vol_index_for_chapter
from app.utils.chapter_numbering import display_chapter_number

logger = logging.getLogger(__name__)

TENSION_WARN_DELTA = 30
TENSION_CRIT_DELTA = 50
BEAT_MATCH_DRIFT = 0.3
SCREEN_TIME_RATIO_WARN = 1.5
SCREEN_TIME_RATIO_CRIT = 1.8


def beat_match_score(planned: str, actual: str) -> float:
    """计划节拍与实际节拍相似度 0~1（启发式，供漂移告警）。"""
    p = (planned or "").strip()
    a = (actual or "").strip()
    if not p or not a:
        return 0.0 if p or a else 1.0
    return SequenceMatcher(None, p, a).ratio()


def _planned_vol_beat(sl: StoryLine, vol_index: int) -> dict | None:
    extra = sl.extra if isinstance(sl.extra, dict) else {}
    for b in extra.get("volume_beats") or []:
        if isinstance(b, dict) and int(b.get("vol_index", -1)) == vol_index:
            return b
    return None


def _crossover_expected_this_vol(sl: StoryLine, vol_index: int) -> bool:
    extra = sl.extra if isinstance(sl.extra, dict) else {}
    for cx in extra.get("crossover_nodes") or []:
        if isinstance(cx, dict) and int(cx.get("at_vol", -1)) == vol_index:
            return True
    return False


def apply_storyline_weave_actuals(
    db: Session,
    project_id: str,
    chapter: Chapter,
    storyline_updates: list[Any],
) -> dict[str, Any]:
    """
    复盘故事线更新后：归档 actual_beats、累计 screen_time，并执行漂移检测。

    Returns:
        drift_report: { corrections, debts_created, warnings }
    """
    ch_no = chapter.sort_order or 0
    vol_index = _vol_index_for_chapter(db, project_id, ch_no)
    corrections: list[str] = []
    debts_created: list[str] = []
    warnings: list[str] = []

    project = db.query(Project).filter(Project.id == project_id).first()
    cumulative_screen: dict[str, int] = {}
    if project and isinstance(project.extra, dict):
        raw = project.extra.get("storyline_screen_time_cumulative") or {}
        if isinstance(raw, dict):
            cumulative_screen = {str(k): int(v) for k, v in raw.items()}

    for su in storyline_updates:
        sl = _resolve_storyline(db, project_id, su)
        if not sl:
            continue

        actual_beat = (getattr(su, "append_beat", None) or getattr(su, "beat", None) or "").strip()
        actual_tension = _coerce_int(getattr(su, "actual_tension", None), default=-1)
        match_score = _coerce_float(getattr(su, "beat_match_score", None), default=-1.0)
        crossover_done = getattr(su, "crossover_executed", None)
        screen_words = _coerce_int(getattr(su, "screen_time_words", None), default=0)

        planned = _planned_vol_beat(sl, vol_index) or {}
        planned_beat = (planned.get("beat") or "").strip()
        planned_tension = int(planned.get("tension") or 0)

        if match_score < 0 and planned_beat and actual_beat:
            match_score = beat_match_score(planned_beat, actual_beat)

        extra = dict(sl.extra) if isinstance(sl.extra, dict) else {}
        actuals = list(extra.get("actual_beats") or [])
        actuals = [a for a in actuals if not (
            isinstance(a, dict) and int(a.get("ch", -1)) == ch_no
        )]
        actuals.append({
            "vol": vol_index,
            "ch": ch_no,
            "beat": actual_beat,
            "planned_beat": planned_beat,
            "actual_tension": actual_tension if actual_tension >= 0 else None,
            "planned_tension": planned_tension,
            "beat_match_score": round(match_score, 3) if match_score >= 0 else None,
            "crossover_executed": crossover_done,
            "screen_time_words": screen_words or None,
        })
        extra["actual_beats"] = actuals[-40:]
        sl.extra = extra
        flag_modified(sl, "extra")

        sid = str(sl.id)
        if screen_words > 0:
            cumulative_screen[sid] = cumulative_screen.get(sid, 0) + screen_words

        if not planned_beat:
            continue

        if match_score >= 0 and match_score < BEAT_MATCH_DRIFT:
            msg = (
                f"「{sl.name}」节拍脱轨：计划「{planned_beat[:30]}」"
                f" vs 实际「{actual_beat[:30]}」（匹配 {match_score:.2f}）"
            )
            warnings.append(msg)
            corrections.append(f"下一章请向计划节拍回归：{planned_beat[:60]}")
            debts_created.append(
                _upsert_storyline_debt(
                    db, project_id, chapter, ch_no,
                    "storyline_drift", "high", msg,
                    f"本章落实：{planned_beat[:120]}",
                ),
            )

        if actual_tension >= 0 and planned_tension > 0:
            delta = abs(actual_tension - planned_tension)
            if delta > TENSION_CRIT_DELTA:
                msg = (
                    f"「{sl.name}」张力偏差 {delta}（计划 {planned_tension}，"
                    f"实际 {actual_tension}）"
                )
                warnings.append(msg)
                corrections.append(f"「{sl.name}」张力欠债 {delta}，本章须拉升/回落 toward {planned_tension}")
                debts_created.append(
                    _upsert_storyline_debt(
                        db, project_id, chapter, ch_no,
                        "storyline_drift", "critical", msg,
                        f"目标张力约 {planned_tension}",
                    ),
                )
            elif delta > TENSION_WARN_DELTA:
                warnings.append(
                    f"「{sl.name}」张力略偏（计划 {planned_tension}，实际 {actual_tension}）",
                )

        if _crossover_expected_this_vol(sl, vol_index) and crossover_done is False:
            msg = f"「{sl.name}」卷 {vol_index} 交叉点未执行"
            corrections.append(f"补写未完成的交叉点：{sl.name} 相关卷级交叉")
            debts_created.append(
                _upsert_storyline_debt(
                    db, project_id, chapter, ch_no,
                    "storyline_crossover", "high", msg,
                    "本章或下章须完成双线交叉并改变两条线轨迹",
                ),
            )

    if project:
        base = dict(project.extra) if isinstance(project.extra, dict) else {}
        base["storyline_screen_time_cumulative"] = cumulative_screen
        weight_checks = _screen_time_imbalance_warnings(db, project_id, cumulative_screen)
        for w in weight_checks:
            warnings.append(w["message"])
            if w.get("correction"):
                corrections.append(w["correction"])
            if w.get("debt"):
                debts_created.append(w["debt"])

        base["storyline_drift_corrections"] = corrections[:8]
        project.extra = base
        flag_modified(project, "extra")

    return {
        "corrections": corrections,
        "debts_created": [d for d in debts_created if d],
        "warnings": warnings,
    }


def _screen_time_imbalance_warnings(
    db: Session,
    project_id: str,
    cumulative: dict[str, int],
) -> list[dict]:
    lines = db.query(StoryLine).filter(StoryLine.project_id == project_id).all()
    out: list[dict] = []
    for sl in lines:
        extra = sl.extra if isinstance(sl.extra, dict) else {}
        weight = float(extra.get("weight") or 0)
        if weight <= 0:
            continue
        words = cumulative.get(str(sl.id), 0)
        if words <= 0:
            continue
        ratio = words / max(weight * 10000, 1)
        if ratio > SCREEN_TIME_RATIO_CRIT:
            msg = f"「{sl.name}」戏份超标约 {int((ratio - 1) * 100)}%（累计 {words} 字）"
            debt_id = _upsert_storyline_debt(
                db, project_id, None, 0,
                "storyline_screen_time", "critical", msg,
                "后续章节减少该线篇幅",
            )
            out.append({
                "message": msg,
                "correction": f"「{sl.name}」已超预算，本章减少该线字数",
                "debt": debt_id,
            })
        elif ratio > SCREEN_TIME_RATIO_WARN:
            out.append({
                "message": f"「{sl.name}」戏份偏重（累计 {words} 字）",
                "correction": f"「{sl.name}」注意控制篇幅",
                "debt": None,
            })
    return out


def _upsert_storyline_debt(
    db: Session,
    project_id: str,
    chapter: Chapter | None,
    ch_no: int,
    issue_type: str,
    severity: str,
    summary: str,
    suggested_fix: str,
) -> str:
    ch_id = str(chapter.id) if chapter else ""
    fp = quality_debt_fingerprint(project_id, ch_id or "none", issue_type, summary)
    debt = db.query(QualityDebt).filter(
        QualityDebt.project_id == project_id,
        QualityDebt.fingerprint == fp,
    ).first()
    if debt:
        debt.severity = severity
        debt.summary = summary[:500]
        debt.suggested_fix = suggested_fix[:500]
        return str(debt.id)
    debt = QualityDebt(
        project_id=project_id,
        chapter_id=chapter.id if chapter else None,
        source_chapter_number=display_chapter_number(
            chapter.title if chapter else None, ch_no,
        ) if chapter else ch_no,
        issue_type=issue_type,
        severity=severity,
        status="pending",
        summary=summary[:500],
        suggested_fix=suggested_fix[:500],
        fingerprint=fp,
    )
    db.add(debt)
    return str(debt.id)


def _resolve_storyline(db: Session, project_id: str, su: Any) -> StoryLine | None:
    from uuid import UUID

    if getattr(su, "storyline_id", None):
        try:
            uid = UUID(str(su.storyline_id))
            return db.query(StoryLine).filter(
                StoryLine.id == uid, StoryLine.project_id == project_id,
            ).first()
        except Exception:
            pass
    if getattr(su, "storyline_name", None):
        return db.query(StoryLine).filter(
            StoryLine.name == su.storyline_name,
            StoryLine.project_id == project_id,
        ).first()
    return None


def _coerce_int(val: Any, default: int = 0) -> int:
    try:
        if val is None:
            return default
        return int(val)
    except (TypeError, ValueError):
        return default


def _coerce_float(val: Any, default: float = -1.0) -> float:
    try:
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def build_weave_matrix_overview(db: Session, project_id: str) -> dict:
    """供前端织网图：计划张力矩阵 + 实际张力 + 漂移项。"""
    lines = (
        db.query(StoryLine)
        .filter(StoryLine.project_id == project_id)
        .order_by(StoryLine.sort_order.asc())
        .all()
    )
    volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order.asc())
        .all()
    )
    n_volumes = max(len(volumes), 1)
    rows = []
    drift_alerts: list[dict] = []

    for sl in lines:
        extra = sl.extra if isinstance(sl.extra, dict) else {}
        planned = {int(b.get("vol_index", -1)): b for b in (extra.get("volume_beats") or []) if isinstance(b, dict)}
        actual_by_vol: dict[int, list[dict]] = {}
        for a in extra.get("actual_beats") or []:
            if isinstance(a, dict):
                v = int(a.get("vol", -1))
                actual_by_vol.setdefault(v, []).append(a)

        vol_cells = []
        for vi in range(n_volumes):
            pb = planned.get(vi) or {}
            acts = actual_by_vol.get(vi) or []
            actual_tensions = [int(x.get("actual_tension") or 0) for x in acts if x.get("actual_tension") is not None]
            avg_actual = int(sum(actual_tensions) / len(actual_tensions)) if actual_tensions else None
            pt = int(pb.get("tension") or 0)
            vol_cells.append({
                "vol_index": vi,
                "planned_tension": pt,
                "actual_tension": avg_actual,
                "beat": pb.get("beat"),
                "is_active": pb.get("is_active", True),
            })
            if avg_actual is not None and pt > 0 and abs(avg_actual - pt) > TENSION_WARN_DELTA:
                drift_alerts.append({
                    "storyline_id": str(sl.id),
                    "storyline_name": sl.name,
                    "vol_index": vi,
                    "message": f"张力偏差 {abs(avg_actual - pt)}",
                })

        rows.append({
            "id": str(sl.id),
            "name": sl.name,
            "line_type": sl.line_type,
            "weight": extra.get("weight"),
            "tension_curve": extra.get("tension_curve") or [],
            "volume_cells": vol_cells,
            "crossover_nodes": extra.get("crossover_nodes") or [],
        })

    return {
        "n_volumes": n_volumes,
        "volume_titles": [v.title for v in volumes],
        "storylines": rows,
        "drift_alerts": drift_alerts[:30],
    }
