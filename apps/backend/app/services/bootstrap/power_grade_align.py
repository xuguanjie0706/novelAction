"""技能/道具品阶与多轴 power registry 对齐。"""

from __future__ import annotations

from typing import Any

from app.services.bootstrap.power_registry import resolve_realm_in_registry

# 旧版 grade → 主轴最低 rank（0-based，无 artifact 轴时兜底）
_GRADE_MIN_PRIMARY_RANK: dict[str, int] = {
    "mortal": 0,
    "earth": 1,
    "sky": 2,
    "profound": 3,
    "saint": 4,
    "divine": 5,
    "supreme": 6,
}

# rarity → 主轴最低 rank 兜底
_RARITY_MIN_PRIMARY_RANK: dict[str, int] = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
    "mythic": 5,
    "unique": 6,
}


def get_axis_level_names(ctx: dict, axis_role: str) -> list[str]:
    """从 ctx.power_systems_full 取指定轴的境界/阶位名（低→高）。"""
    names: list[str] = []
    for snap in ctx.get("power_systems_full") or []:
        if (snap.get("axis_role") or "primary") != axis_role:
            continue
        for lv in snap.get("levels") or []:
            if isinstance(lv, dict) and (lv.get("name") or "").strip():
                names.append((lv.get("name") or "").strip())
    return names


def _registry_axis_rank(registry: dict, name: str | None, axis: str) -> int | None:
    if not name or not registry:
        return None
    resolved = resolve_realm_in_registry(name, registry)
    key = resolved or name
    meta = registry.get(key)
    if not meta or meta.get("axis") != axis:
        # 允许用 raw_name 再搜
        for k, m in registry.items():
            if m.get("axis") == axis and (
                m.get("raw_name") == name or k == name or name in k
            ):
                meta = m
                key = k
                break
        else:
            return None
    rank = meta.get("rank")
    if isinstance(rank, int):
        return rank
    try:
        return int(rank)
    except (TypeError, ValueError):
        return None


def min_primary_rank_for_grade(grade: str | None, ctx: dict) -> int:
    """grade/rarity 映射到主轴最低 rank。"""
    g = (grade or "").strip().lower()
    if g in _GRADE_MIN_PRIMARY_RANK:
        return _GRADE_MIN_PRIMARY_RANK[g]
    if g in _RARITY_MIN_PRIMARY_RANK:
        return _RARITY_MIN_PRIMARY_RANK[g]
    artifact_names = get_axis_level_names(ctx, "artifact")
    if artifact_names and g:
        for i, nm in enumerate(artifact_names):
            if g in nm.lower() or nm in g:
                return min(i + 2, len(ctx.get("power_level_names") or []) - 1)
    return 1


def pick_primary_realm_at_rank(ctx: dict, min_rank: int) -> str | None:
    """取主轴上 rank ≥ min_rank 的第一个 canonical 境界名。"""
    names = ctx.get("power_level_names") or []
    registry = ctx.get("power_level_registry") or {}
    for i, nm in enumerate(names):
        if i >= min_rank:
            resolved = resolve_realm_in_registry(nm, registry)
            return resolved or nm
    return names[-1] if names else None


def enrich_skill_power_fields(item: dict, ctx: dict) -> dict[str, Any]:
    """
    归一技能的力量引用：required_realm / artifact_tier / required_path → power_ref。

    @returns extra 字段片段 + 规范化 level_required
    """
    registry = ctx.get("power_level_registry") or {}
    out: dict[str, Any] = {}

    req_realm = (item.get("required_realm") or item.get("level_required") or "").strip()
    resolved = resolve_realm_in_registry(req_realm, registry) if req_realm else None
    if resolved:
        out["level_required"] = resolved
        meta = registry.get(resolved) or {}
        out["power_ref"] = {
            "realm": resolved,
            "axis": meta.get("axis", "primary"),
            "rank": meta.get("rank"),
        }
    elif req_realm:
        min_r = min_primary_rank_for_grade(item.get("grade"), ctx)
        fallback = pick_primary_realm_at_rank(ctx, min_r)
        if fallback:
            out["level_required"] = fallback
            out["power_ref"] = {"realm": fallback, "axis": "primary", "inferred_from": "grade"}
    else:
        min_r = min_primary_rank_for_grade(item.get("grade"), ctx)
        fallback = pick_primary_realm_at_rank(ctx, min_r)
        if fallback:
            out["level_required"] = fallback
            out["power_ref"] = {"realm": fallback, "axis": "primary", "inferred_from": "grade"}

    artifact_tier = (item.get("artifact_tier") or "").strip()
    if artifact_tier:
        resolved_a = resolve_realm_in_registry(artifact_tier, registry)
        if resolved_a:
            out["artifact_tier"] = resolved_a
        else:
            out["artifact_tier"] = artifact_tier

    path_req = (item.get("required_path") or "").strip()
    path_rank_name = (item.get("required_path_rank") or "").strip()
    if path_req or path_rank_name:
        pr: dict[str, Any] = {"path_id": path_req}
        if path_rank_name:
            pr["path_rank_name"] = path_rank_name
            r = _registry_axis_rank(registry, path_rank_name, "path")
            if r is not None:
                pr["path_rank"] = r
        out["path_ref"] = pr

    return out


def enrich_item_power_fields(item: dict, ctx: dict) -> dict[str, Any]:
    """归一道具的力量引用：required_realm + artifact_tier。"""
    registry = ctx.get("power_level_registry") or {}
    out: dict[str, Any] = {}

    tier = (item.get("artifact_tier") or item.get("required_artifact_tier") or "").strip()
    if not tier and item.get("rarity"):
        min_r = min_primary_rank_for_grade(item.get("rarity"), ctx)
        artifact_names = get_axis_level_names(ctx, "artifact")
        if artifact_names and min_r < len(artifact_names):
            tier = artifact_names[min_r]
    if tier:
        resolved = resolve_realm_in_registry(tier, registry)
        out["artifact_tier"] = resolved or tier
        meta = registry.get(resolved or "") or {}
        if meta.get("axis") == "artifact":
            out["power_ref"] = {"artifact_tier": resolved or tier, "rank": meta.get("rank")}

    req_realm = (item.get("required_realm") or "").strip()
    if req_realm:
        resolved_r = resolve_realm_in_registry(req_realm, registry)
        if resolved_r:
            out["required_realm"] = resolved_r
            if "power_ref" not in out:
                out["power_ref"] = {}
            out["power_ref"]["realm"] = resolved_r
    elif tier and "required_realm" not in out:
        min_r = min_primary_rank_for_grade(item.get("rarity"), ctx)
        fallback = pick_primary_realm_at_rank(ctx, min_r)
        if fallback:
            out["required_realm"] = fallback

    return out
