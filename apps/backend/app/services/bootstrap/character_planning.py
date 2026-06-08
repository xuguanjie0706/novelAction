"""人物规划字段 vs 现状字段（Bootstrap 期）。

卷纲 / antagonist_ladder 属于设计层；``Character.current_realm`` 是故事起点现状，
不得由卷纲生成回写。arc Boss 的规划峰值存 ``extra.peak_realm``（对决境）。
"""
from __future__ import annotations

from typing import Any

from app.services.bootstrap.antagonist_roster import (
    apply_ladder_fields_to_character,
    ladder_entry_by_name,
)
from app.services.bootstrap.power_registry import resolve_realm_in_registry


def planning_peak_realm(char: Any) -> str:
    """读取人物规划峰值境界（对决境）；无则空串。"""
    extra = char.extra if isinstance(getattr(char, "extra", None), dict) else {}
    return (extra.get("peak_realm") or "").strip()


def _canonical_level_name(
    name: str,
    *,
    level_names: list[str],
    registry: dict,
) -> str:
    """将境界展示名归一到主轴阶位名（如「大斗师初期」→「大斗师」）。"""
    name = (name or "").strip()
    if not name:
        return ""
    if registry:
        resolved = resolve_realm_in_registry(name, registry)
        if resolved:
            return resolved
    for ln in sorted(level_names, key=len, reverse=True):
        if ln and ln in name:
            return ln
    return name


def realms_equivalent(
    a: str | None,
    b: str | None,
    *,
    level_names: list[str],
    registry: dict | None = None,
) -> bool:
    """判断两境界名是否指向同一阶（含子境模糊）。"""
    reg = registry or {}
    ca = _canonical_level_name(a or "", level_names=level_names, registry=reg)
    cb = _canonical_level_name(b or "", level_names=level_names, registry=reg)
    return bool(ca and cb and ca == cb)


def normalize_roster_boss_planning(
    char: Any,
    entry: dict,
    *,
    registry: dict | None = None,
    level_names: list[str] | None = None,
) -> bool:
    """对齐 arc Boss 规划字段；仅纠正「对决境误写入 current_realm」。

    Returns:
        是否修改了人物字段。
    """
    registry = registry or {}
    level_names = level_names or []
    changed = False
    extra = dict(char.extra) if isinstance(getattr(char, "extra", None), dict) else {}

    climax = (entry.get("realm_at_climax") or "").strip()
    debut = (entry.get("realm_at_debut") or "").strip()
    apply_ladder_fields_to_character(extra, entry)

    if climax and extra.get("peak_realm") != climax:
        extra["peak_realm"] = climax
        changed = True

    char.extra = extra if extra else None

    is_arc_boss = (
        getattr(char, "character_tier", None) == "arc"
        or getattr(char, "role", None) == "antagonist"
    )
    if not is_arc_boss or not debut:
        return changed

    current = (char.current_realm or "").strip()
    if not current:
        char.current_realm = debut
        return True

    if climax and realms_equivalent(
        current, climax, level_names=level_names, registry=registry,
    ) and not realms_equivalent(current, debut, level_names=level_names, registry=registry):
        char.current_realm = debut
        changed = True
    return changed


def normalize_roster_boss_characters(characters: list[Any], ctx: dict) -> int:
    """Step 5 落库后：批量对齐登记表 Boss 的规划字段。"""
    registry: dict = ctx.get("power_level_registry") or {}
    level_names: list[str] = list(ctx.get("power_level_names") or [])
    updated = 0
    for char in characters:
        name = (getattr(char, "name", None) or "").strip()
        if not name:
            continue
        entry = ladder_entry_by_name(ctx, name)
        if not entry:
            continue
        if normalize_roster_boss_planning(
            char, entry, registry=registry, level_names=level_names,
        ):
            updated += 1
    return updated


def build_character_realm_audit_lines(db: Any, project_id: Any) -> str:
    """一致性扫描用：区分 current_realm（现状）与 peak_realm（规划）。"""
    from app.models import Character

    chars = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.name)
        .all()
    )
    if not chars:
        return "（未设定）"
    lines: list[str] = []
    for c in chars:
        peak = planning_peak_realm(c)
        tier = getattr(c, "character_tier", None) or ""
        if peak:
            lines.append(
                f"- {c.name}（{tier or '？'}）：current_realm={c.current_realm or '未知'}"
                f"，peak_realm(规划对决)={peak}"
            )
        else:
            lines.append(f"- {c.name}：current_realm={c.current_realm or '未知'}")
    return "\n".join(lines)
