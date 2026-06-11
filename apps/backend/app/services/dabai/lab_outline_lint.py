"""dabai 实验书架卷纲质检 — 从 dabai_* 表重建全书章纲并跑 dabai/linter。

单一事实来源：bootstrap 收尾、卷展开完成、手动 relint 均调用
``run_dabai_project_linter``，结果写入 ``DabaiProject.linter_report``。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from dabai.config import DabaiConfig
from dabai.linter import Issue, LinterReport, lint_chapters

from app.models.dabai import DabaiChapterOutline, DabaiProject, DabaiVolume

logger = logging.getLogger(__name__)


def cfg_from_project(project: DabaiProject) -> DabaiConfig:
    """从项目 meta 重建 DabaiConfig（linter 规则阈值与 bootstrap 一致）。"""
    meta = project.meta or {}
    return DabaiConfig(
        logline=project.logline or "",
        mock=False,
        volume_count=int(meta.get("volume_count", 6)),
        volume_chapters=int(meta.get("volume_chapters", 30)),
        chapter_batch_size=int(meta.get("chapter_batch_size", 30)),
        big_beat_every=int(meta.get("big_beat_every", 5)),
    )


def _realm_max(project: DabaiProject) -> int | None:
    levels = (project.power_ladder or {}).get("levels") or []
    ranks = [int(l.get("rank", 0)) for l in levels if str(l.get("rank", "")).strip()]
    return max(ranks) if ranks else None


def _volume_dicts(volumes: list[DabaiVolume]) -> list[dict]:
    return [
        {
            "volume_number": v.volume_number,
            "title": v.title,
            "phase": v.phase,
            "planned_chapters": int(v.planned_chapters or 0),
            "realm_start_rank": v.realm_start_rank,
            "realm_end_rank": v.realm_end_rank,
        }
        for v in volumes
    ]


def _chapter_dict(ch: DabaiChapterOutline) -> dict:
    return {
        "chapter_number": ch.chapter_number,
        "title": ch.title,
        "shuang_type": ch.shuang_type or "",
        "yaqu_setup": ch.yaqu_setup or "",
        "emotion_turn": ch.emotion_turn or "",
        "yinbao": ch.yinbao or "",
        "shuang_payoff": ch.shuang_payoff or "",
        "witnesses": ch.witnesses or [],
        "end_hook": ch.end_hook or "",
        "new_info_count": ch.new_info_count or 1,
        "is_big_beat": bool(ch.is_big_beat),
        "realm_rank": ch.realm_rank,
    }


def _chapter_ranges(volumes: list[dict]) -> list[tuple[int, int, dict]]:
    """返回 [(global_start, global_end, vol_dict), ...]。"""
    ranges: list[tuple[int, int, dict]] = []
    start = 1
    for vol in volumes:
        planned = max(int(vol.get("planned_chapters") or 0), 1)
        ranges.append((start, start + planned - 1, vol))
        start += planned
    return ranges


def _realm03_issues(ch_dicts: list[dict], volumes: list[dict]) -> list[Issue]:
    """全书 lint 不传 realm_range 时 REALM-03 不触发；按卷区间补检。"""
    extra: list[Issue] = []
    for g_lo, g_hi, vol in _chapter_ranges(volumes):
        vr_lo, vr_hi = vol.get("realm_start_rank"), vol.get("realm_end_rank")
        for ch in ch_dicts:
            num = ch["chapter_number"]
            if not (g_lo <= num <= g_hi):
                continue
            rr = ch.get("realm_rank")
            if not isinstance(rr, int):
                continue
            if (vr_lo and rr < vr_lo) or (vr_hi and rr > vr_hi):
                extra.append(Issue(
                    "REALM-03", "medium", num,
                    f"realm_rank={rr} 跳出第{vol.get('volume_number')}卷区间"
                    f"[{vr_lo}~{vr_hi}]",
                    "本卷境界须落在卷区间内",
                ))
    return extra


def _pending_report() -> dict:
    return {
        "status": "pending",
        "score": None,
        "issue_count": 0,
        "critical_count": 0,
        "issues": [],
        "chapter_count": 0,
        "linted_at": None,
    }


def run_dabai_project_linter(
    db: Session,
    project: DabaiProject,
    cfg: DabaiConfig | None = None,
) -> dict:
    """读库全书章纲 → lint_chapters → 写回 project.linter_report 并 commit。

    Args:
        db: SQLAlchemy session。
        project: 目标 dabai 项目（须已 flush 章纲）。
        cfg: 可选；缺省从 project.meta 推导。

    Returns:
        linter 报告 dict（与 ``dabai/linter.LinterReport.as_dict`` 同形，增 linted_at/chapter_count）。
    """
    cfg = cfg or cfg_from_project(project)
    chapters = (
        db.query(DabaiChapterOutline)
        .filter(DabaiChapterOutline.project_id == project.id)
        .order_by(DabaiChapterOutline.chapter_number)
        .all()
    )
    if not chapters:
        report = _pending_report()
        project.linter_report = report
        db.commit()
        db.refresh(project)
        return report

    volumes = (
        db.query(DabaiVolume)
        .filter(DabaiVolume.project_id == project.id)
        .order_by(DabaiVolume.volume_number)
        .all()
    )
    ch_dicts = [_chapter_dict(c) for c in chapters]
    vol_dicts = _volume_dicts(volumes)
    gf_name = (project.golden_finger or {}).get("name", "")

    base = lint_chapters(
        ch_dicts, cfg,
        realm_max=_realm_max(project),
        realm_range=None,
        volumes=vol_dicts,
        golden_finger_name=gf_name,
    )
    extra = _realm03_issues(ch_dicts, vol_dicts)
    merged = LinterReport(issues=list(base.issues) + extra)
    report = merged.as_dict()
    report["chapter_count"] = len(chapters)
    report["linted_at"] = datetime.now(timezone.utc).isoformat()

    project.linter_report = report
    db.commit()
    db.refresh(project)
    logger.info(
        "dabai lab outline lint project=%s status=%s issues=%d chapters=%d",
        project.id, report.get("status"), report.get("issue_count"), len(chapters),
    )
    return report
