"""Step 2 境界体系落库与 ctx 同步。"""

from __future__ import annotations

from typing import Any

from app.models import PowerSystem, Project
from app.services.bootstrap.parse import coerce_power_system_rank
from app.services.bootstrap.power_registry import merge_power_into_ctx


def _persist_one_system(
    svc: Any,
    project: Project,
    item: dict,
    sort_order: int,
) -> PowerSystem:
    levels = item.get("levels") or []
    if not isinstance(levels, list):
        levels = []
    start_raw = item.get("protagonist_start_rank")
    if start_raw is None:
        start_raw = item.get("protagonist_current_rank")
    end_raw = item.get("protagonist_end_rank")

    extra: dict[str, Any] = {}
    for key in ("axis_role", "visualization", "path_id", "cross_system_rules", "qualitative_leap_tags"):
        if item.get(key) is not None:
            extra[key] = item[key]

    ps = PowerSystem(
        project_id=project.id,
        name=item.get("name", "修炼体系"),
        system_type=item.get("system_type", "cultivation"),
        description=item.get("description"),
        cultivation_method=item.get("cultivation_method"),
        breakthrough_condition=item.get("breakthrough_condition"),
        special_rules=item.get("special_rules"),
        levels=levels,
        protagonist_current_rank=coerce_power_system_rank(start_raw, levels, 1),
        protagonist_end_rank=coerce_power_system_rank(end_raw, levels, None),
        sort_order=sort_order,
        extra=extra if extra else None,
    )
    svc.db.add(ps)
    return ps


def persist_legacy_systems(svc: Any, project: Project, data: list) -> list[PowerSystem]:
    """旧格式 JSON 数组 → 多条 PowerSystem。"""
    results: list[PowerSystem] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        if not item.get("axis_role"):
            item["axis_role"] = "primary" if i == 0 else "secondary"
        results.append(_persist_one_system(svc, project, item, i))
    svc.db.commit()
    return results


def persist_xianxia_bundle(
    svc: Any,
    project: Project,
    bundle: dict[str, Any],
) -> list[PowerSystem]:
    """修仙多轴 JSON 对象 → PowerSystem + Project.extra。"""
    systems = bundle.get("systems") or []
    if not isinstance(systems, list):
        systems = []

    extra = dict(project.extra or {})
    laws = bundle.get("cultivation_laws")
    if isinstance(laws, dict):
        extra["cultivation_laws"] = laws
    dao = bundle.get("dao_heart")
    if isinstance(dao, dict):
        extra["dao_heart"] = dao
    extra["power_architecture"] = {
        "version": 1,
        "axis_count": len(systems),
        "axes": [
            (s.get("axis_role") or "primary")
            for s in systems
            if isinstance(s, dict)
        ],
    }
    project.extra = extra

    results: list[PowerSystem] = []
    for i, item in enumerate(systems):
        if not isinstance(item, dict):
            continue
        results.append(_persist_one_system(svc, project, item, i))

    svc.db.commit()
    return results


def sync_ctx_after_persist(
    ctx: dict,
    project: Project,
    results: list[PowerSystem],
) -> None:
    """落库后刷新 ctx（全保真 registry）。"""
    extra = project.extra if isinstance(project.extra, dict) else {}
    merge_power_into_ctx(
        ctx,
        results,
        project=project,
        cultivation_laws=extra.get("cultivation_laws"),
        dao_heart=extra.get("dao_heart"),
    )
