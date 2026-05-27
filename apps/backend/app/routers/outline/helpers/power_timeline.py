"""卷级结构化战力时间轴聚合。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Character, OutlineNode, PowerSystem, Project
from app.routers.outline.helpers.power_timeline_lanes import build_character_realm_lanes
from app.routers.outline.helpers.realm_whitelist import build_realm_rank_map
from app.services.bootstrap.realm_effective import effective_realm_score

POWER_TIMELINE_EXTRA_KEY = "power_timeline_table_v1"


def _safe_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _rank_for_label(label: str, name_to_rank: dict[str, int]) -> int | None:
    s = (label or "").strip()
    if not s:
        return None
    if s in name_to_rank:
        return int(name_to_rank[s])
    best_rank: int | None = None
    best_len = 0
    for name, rank in name_to_rank.items():
        if not isinstance(name, str) or len(name) < 2:
            continue
        if name in s and len(name) >= best_len:
            best_len = len(name)
            best_rank = int(rank)
    return best_rank


def _trend(cur: float | None, prev: float | None) -> str:
    if prev is None or cur is None:
        return "first"
    if cur > prev:
        return "up"
    if cur < prev:
        return "down"
    return "equal"


def _compute_rows(db: Session, project: Project) -> list[dict[str, Any]]:
    power_systems = (
        db.query(PowerSystem)
        .filter(PowerSystem.project_id == project.id)
        .order_by(PowerSystem.created_at.asc())
        .all()
    )
    name_to_rank, _, _ = build_realm_rank_map(power_systems)
    volumes = (
        db.query(OutlineNode)
        .filter(OutlineNode.project_id == project.id, OutlineNode.node_type == "volume")
        .order_by(OutlineNode.sort_order.asc(), OutlineNode.created_at.asc())
        .all()
    )
    rows: list[dict[str, Any]] = []
    prev_boss_major: int | None = None
    prev_boss_effective: float | None = None
    for idx, vol in enumerate(volumes, start=1):
        extra = vol.extra if isinstance(vol.extra, dict) else {}
        p_start = str(extra.get("protagonist_realm_start") or "").strip()
        p_end = str(extra.get("protagonist_realm_end") or "").strip()
        boss_name = str(extra.get("volume_boss") or "").strip()
        boss_realm = str(extra.get("volume_boss_realm") or "").strip()
        boss_character_id = extra.get("volume_boss_character_id")

        p_start_rank = _rank_for_label(p_start, name_to_rank)
        p_end_rank = _rank_for_label(p_end, name_to_rank)
        boss_major_rank = _rank_for_label(boss_realm, name_to_rank)
        boss_effective = (
            effective_realm_score(boss_major_rank, boss_realm) if boss_major_rank is not None else None
        )
        delta = None
        if boss_major_rank is not None and p_end_rank is not None:
            delta = int(boss_major_rank - p_end_rank)

        rows.append(
            {
                "volume_order": idx,
                "volume_id": str(vol.id),
                "volume_title": vol.title or f"第{idx}卷",
                "phase": vol.phase or "",
                "protagonist_realm_start": p_start or None,
                "protagonist_rank_start": p_start_rank,
                "protagonist_realm_end": p_end or None,
                "protagonist_rank_end": p_end_rank,
                "boss_name": boss_name or None,
                "boss_character_id": str(boss_character_id) if boss_character_id else None,
                "boss_realm": boss_realm or None,
                "boss_major_rank": boss_major_rank,
                "boss_effective_score": round(boss_effective, 2) if boss_effective is not None else None,
                "boss_vs_prev_major": _trend(
                    float(boss_major_rank) if boss_major_rank is not None else None,
                    float(prev_boss_major) if prev_boss_major is not None else None,
                ),
                "boss_vs_prev_effective": _trend(boss_effective, prev_boss_effective),
                "boss_vs_protagonist_end_delta": delta,
            }
        )
        prev_boss_major = boss_major_rank
        prev_boss_effective = boss_effective
    return rows


def _build_realm_scale(power_systems) -> list[dict[str, Any]]:
    """境界阶梯 Y 轴刻度（大境 rank + 名称）。"""
    seen: dict[int, str] = {}
    for system in power_systems or []:
        levels = getattr(system, "levels", None)
        if not isinstance(levels, list):
            continue
        for level in levels:
            if not isinstance(level, dict):
                continue
            name = (level.get("name") or "").strip()
            rank = level.get("rank")
            if not name or not isinstance(rank, int) or rank <= 0:
                continue
            if rank not in seen or len(name) > len(seen[rank]):
                seen[rank] = name
    return [{"rank": r, "name": seen[r]} for r in sorted(seen.keys())]


def _build_chart_series(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """折线图点位：主角起止 + 卷 Boss。"""
    protagonist: list[dict[str, Any]] = []
    boss: list[dict[str, Any]] = []
    for row in rows:
        vo = int(row["volume_order"])
        phase = row.get("phase") or ""
        p_start = row.get("protagonist_realm_start")
        p_end = row.get("protagonist_realm_end")
        prs = row.get("protagonist_rank_start")
        pre = row.get("protagonist_rank_end")
        if p_start and prs is not None:
            protagonist.append({
                "volume_order": vo,
                "realm_label": p_start,
                "major_rank": prs,
                "effective_score": round(effective_realm_score(int(prs), str(p_start)), 2),
                "point_kind": "protagonist_start",
                "phase": phase,
            })
        if p_end and pre is not None:
            protagonist.append({
                "volume_order": vo,
                "realm_label": p_end,
                "major_rank": pre,
                "effective_score": round(effective_realm_score(int(pre), str(p_end)), 2),
                "point_kind": "protagonist_end",
                "phase": phase,
            })
        boss_realm = row.get("boss_realm")
        boss_rank = row.get("boss_major_rank")
        if boss_realm and boss_rank is not None:
            boss.append({
                "volume_order": vo,
                "realm_label": boss_realm,
                "major_rank": boss_rank,
                "effective_score": row.get("boss_effective_score"),
                "point_kind": "volume_boss",
                "boss_name": row.get("boss_name"),
                "phase": phase,
            })
    return {"protagonist": protagonist, "boss": boss}


def build_power_timeline(
    db: Session,
    project_id: uuid.UUID,
    *,
    persist: bool = False,
) -> dict[str, Any]:
    """构建卷级结构化战力时间轴，可选持久化到 Project.extra。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {
            "rows": [],
            "updated_at": None,
            "realm_scale": [],
            "chart": {"protagonist": [], "boss": []},
            "character_lanes": [],
            "volume_count": 0,
        }

    power_systems = (
        db.query(PowerSystem)
        .filter(PowerSystem.project_id == project_id)
        .order_by(PowerSystem.created_at.asc())
        .all()
    )
    name_to_rank, _, _ = build_realm_rank_map(power_systems)
    rows = _compute_rows(db, project)
    characters = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.created_at.asc())
        .all()
    )
    realm_scale = _build_realm_scale(power_systems)
    chart = _build_chart_series(rows)
    character_lanes = build_character_realm_lanes(
        project, characters, rows, name_to_rank, _rank_for_label,
    )
    updated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "rows": rows,
        "updated_at": updated_at,
        "realm_scale": realm_scale,
        "chart": chart,
        "character_lanes": character_lanes,
        "volume_count": len(rows),
    }

    if persist:
        extra = dict(project.extra or {})
        extra[POWER_TIMELINE_EXTRA_KEY] = payload
        project.extra = extra
        db.add(project)
        db.commit()
        db.refresh(project)

    return payload
