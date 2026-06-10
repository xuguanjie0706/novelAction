"""dabai Bootstrap 产物收敛：对立面登记表 ↔ 人物 ↔ 卷骨架 对齐。"""
from __future__ import annotations

import re
from typing import Any

from app.services.bootstrap.power_registry import resolve_realm_in_registry

_PLACEHOLDER_BOSS_RE = re.compile(r"^卷\s*\d+\s*Boss$", re.IGNORECASE)
_ANTAGONIST_ROLE_HINTS = ("反派", "antagonist", "打脸", "boss", "压迫")


def is_placeholder_boss_name(name: str) -> bool:
    """检测 LLM 占位 Boss 名（如「卷1Boss」）。"""
    n = (name or "").strip()
    if not n:
        return True
    return bool(_PLACEHOLDER_BOSS_RE.match(n))


def coerce_dabai_ladder_raw(raw: list | None) -> list[dict]:
    """dabai cast_world 字段 → antagonist_roster 契约（vol_index / realm_at_climax）。"""
    out: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if row.get("vol_index") is None:
            vn = row.get("volume_number")
            try:
                row["vol_index"] = int(vn) - 1 if vn is not None else None
            except (TypeError, ValueError):
                row["vol_index"] = None
        if not row.get("realm_at_climax") and row.get("boss_realm"):
            row["realm_at_climax"] = row["boss_realm"]
        if not row.get("realm_at_debut"):
            row["realm_at_debut"] = row.get("realm_at_debut") or row.get("boss_realm") or ""
        if not row.get("boss_name") and row.get("name"):
            row["boss_name"] = row["name"]
        out.append(row)
    return out


def _antagonist_candidates(character_rows: list[dict]) -> list[str]:
    names: list[str] = []
    for c in character_rows:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip()
        if not name:
            continue
        role = str(c.get("role") or "").lower()
        tier = str(c.get("tier") or "").lower()
        if any(h in role for h in _ANTAGONIST_ROLE_HINTS) or tier == "arc":
            names.append(name)
    return names


def bind_ladder_boss_names_to_characters(
    ladder_raw: list[dict],
    character_rows: list[dict],
) -> list[dict]:
    """占位 Boss 名替换为 characters 里已生成的反派/打脸角色名。"""
    pool = _antagonist_candidates(character_rows)
    used: set[str] = set()
    pool_i = 0
    out: list[dict] = []
    for item in ladder_raw:
        row = dict(item)
        name = (row.get("boss_name") or row.get("name") or "").strip()
        if is_placeholder_boss_name(name):
            while pool_i < len(pool):
                cand = pool[pool_i]
                pool_i += 1
                if cand not in used:
                    name = cand
                    break
            if is_placeholder_boss_name(name):
                vi = row.get("vol_index")
                try:
                    vol_n = int(vi) + 1 if vi is not None else len(out) + 1
                except (TypeError, ValueError):
                    vol_n = len(out) + 1
                faction = (row.get("faction") or "").strip()
                hook = (row.get("face_slap_hook") or row.get("narrative_function") or "").strip()
                if faction:
                    name = f"{faction}·{hook[:6] or '镇守者'}"[:20]
                else:
                    name = f"{hook[:6] or '镇守者'}·卷{vol_n}"[:20]
        row["boss_name"] = name
        used.add(name)
        out.append(row)
    return out


def normalize_dabai_character_role(role: str | None) -> tuple[str, str | None]:
    """大白文 AI 角色标签 → 库内 canonical role（protagonist/antagonist/supporting/neutral）。

    Returns:
        (canonical_role, dabai_role_label) — 非标准中文标签保留在 extra 供 UI 展示。
    """
    raw = (role or "").strip() or "supporting"
    if raw in ("protagonist", "antagonist", "supporting", "neutral"):
        return raw, None
    direct = {
        "主角": "protagonist",
        "男主": "protagonist",
        "反派": "antagonist",
        "女主": "supporting",
        "配角": "supporting",
        "中立": "neutral",
    }
    if raw in direct:
        return direct[raw], raw
    lower = raw.lower()
    if "打脸" in raw or "boss" in lower or "压迫" in raw:
        return "antagonist", raw
    if "主角" in raw or "男主" in raw:
        return "protagonist", raw
    if "反派" in raw:
        return "antagonist", raw
    return "supporting", raw


def normalize_dabai_character_realm(
    realm: str | None,
    ctx: dict,
    *,
    is_protagonist: bool = False,
) -> str | None:
    """将人物境界对齐本书 PowerSystem 主轴名（消歧义练气/筑基/凡人）。"""
    level_names: list[str] = list(ctx.get("power_level_names") or [])
    registry: dict = ctx.get("power_level_registry") or {}
    if not level_names:
        return (realm or "").strip() or None

    raw = (realm or "").strip()
    if is_protagonist and (not raw or "凡人" in raw or "灵根" in raw or raw in ("无", "无境界")):
        return level_names[0]

    if raw:
        resolved = resolve_realm_in_registry(raw, registry) if registry else None
        if resolved and resolved in level_names:
            return resolved
        if raw in level_names:
            return raw
        if "练气" in raw or "凡人" in raw:
            return level_names[0]
        if "筑基" in raw and len(level_names) > 1:
            return level_names[1]
        if "金丹" in raw and len(level_names) > 2:
            return level_names[2]
    return raw or (level_names[0] if is_protagonist else None)


def repair_dabai_volume_boss_binding(svc: Any, project: Any, ctx: dict) -> int:
    """存量书：从 antagonist_ladder 回填各卷 volume_boss（无 LLM）。"""
    from sqlalchemy.orm.attributes import flag_modified

    from app.models import Character, OutlineNode
    from app.services.bootstrap.antagonist_roster import (
        bind_volume_boss_from_roster,
        load_antagonist_ladder,
    )

    ladder = load_antagonist_ladder(project)
    if not ladder:
        ladder = ctx.get("antagonist_ladder") or []
    if not ladder:
        return 0

    chars = svc.db.query(Character).filter(Character.project_id == project.id).all()
    sync_ctx_char_maps(ctx, chars)
    ctx["antagonist_ladder"] = ladder

    volumes = (
        svc.db.query(OutlineNode)
        .filter(OutlineNode.project_id == project.id, OutlineNode.node_type == "volume")
        .order_by(OutlineNode.sort_order)
        .all()
    )
    fixed = 0
    for vol in volumes:
        vi = int(vol.sort_order or 0)
        extra = dict(vol.extra or {})
        before = (extra.get("volume_boss") or "").strip()
        bind_volume_boss_from_roster(vi, {}, extra, ctx)
        after = (extra.get("volume_boss") or "").strip()
        if after and before != after:
            vol.extra = extra
            flag_modified(vol, "extra")
            fixed += 1
    if fixed:
        svc.db.commit()
    return fixed


def sync_ctx_char_maps(ctx: dict, characters: list[Any]) -> None:
    """刷新 ctx 人物索引，供 bind_volume_boss / skills_items 挂 UUID。"""
    named = [c for c in characters if getattr(c, "name", None)]
    ctx["characters"] = [
        {"name": c.name, "role": getattr(c, "role", "")}
        for c in named
    ]
    ctx["char_name_to_id"] = {
        c.name: str(c.id) for c in named if getattr(c, "id", None)
    }
    ctx["char_id_list"] = [
        {"id": str(c.id), "name": c.name} for c in named if getattr(c, "id", None)
    ]
    ctx["_char_ids"] = [str(c.id) for c in named if getattr(c, "id", None)]
    protag = next(
        (c for c in characters if getattr(c, "role", "") in ("主角", "protagonist")),
        None,
    )
    if protag:
        ctx["protagonist"] = protag.name
