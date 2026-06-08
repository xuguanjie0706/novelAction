"""卷级对立面 roster：生成约束、落库绑定与交叉校验。"""
from __future__ import annotations

import logging
from typing import Any

from app.services.bootstrap.power_registry import resolve_realm_in_registry
from app.services.bootstrap.protagonist_progression import (
    compute_book_realm_endpoints,
    compute_vol_end_ranks,
)

logger = logging.getLogger(__name__)

LADDER_EXTRA_KEY = "antagonist_ladder"


def load_antagonist_ladder(project: Any) -> list[dict]:
    """从 Project.extra 读取 antagonist_ladder。"""
    extra = getattr(project, "extra", None) or {}
    if not isinstance(extra, dict):
        return []
    raw = extra.get(LADDER_EXTRA_KEY)
    return raw if isinstance(raw, list) else []


def _resolve_realm_rank(
    realm_name: str | None,
    rank_map: dict[str, int],
    level_names: list[str],
    registry: dict,
) -> int:
    if not realm_name or not str(realm_name).strip():
        return -1
    name = str(realm_name).strip()
    resolved = resolve_realm_in_registry(name, registry) if registry else name
    canonical = resolved or name
    if canonical in rank_map:
        return rank_map[canonical]
    for ln in sorted(level_names, key=len, reverse=True):
        if ln and (ln in canonical or canonical in ln):
            return rank_map.get(ln, -1)
    return -1


def _fallback_boss_ranks(ctx: dict, n_volumes: int) -> list[tuple[int, int]]:
    """每卷 (debut_rank, climax_rank) 兜底，**0-based** 与 ``rank_map`` 一致。"""
    endpoints = compute_book_realm_endpoints(ctx)
    vol_ends = compute_vol_end_ranks(ctx, n_volumes)
    level_names: list[str] = list(ctx.get("power_level_names") or [])
    if not endpoints or not vol_ends or not level_names:
        return [(0, min(1, len(level_names) - 1))] * max(1, n_volumes)

    book_start, end_rank, _ = endpoints  # 1-based（protagonist_progression）
    max_idx = len(level_names) - 1
    pairs: list[tuple[int, int]] = []
    prev_climax = -1
    for i, protag_end in enumerate(vol_ends):
        start_idx = (book_start - 1) if i == 0 else max(0, vol_ends[i - 1] - 1)
        protag_end_idx = max(0, protag_end - 1)
        climax_idx = min(max(protag_end_idx + 1, start_idx + 1), max_idx)
        if climax_idx <= prev_climax:
            climax_idx = min(prev_climax + 1, max_idx)
        pairs.append((max(0, start_idx), climax_idx))
        prev_climax = climax_idx
    if pairs:
        end_idx = min(max(end_rank - 1, 0), max_idx)
        pairs[-1] = (pairs[-1][0], max(pairs[-1][1], end_idx))
    return pairs


def normalize_antagonist_ladder(raw: list | None, ctx: dict, n_volumes: int) -> list[dict]:
    """清洗 AI roster，补齐 vol_index / 境界名 / rank，长度对齐卷数。"""
    level_names: list[str] = list(ctx.get("power_level_names") or [])
    rank_map = {name: i for i, name in enumerate(level_names)}
    registry: dict = ctx.get("power_level_registry") or {}
    fallback_pairs = _fallback_boss_ranks(ctx, n_volumes)

    by_index: dict[int, dict] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            vi = item.get("vol_index")
            if vi is None:
                vi = item.get("volume_index")
            try:
                idx = int(vi)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < n_volumes:
                by_index[idx] = dict(item)

    out: list[dict] = []
    for i in range(n_volumes):
        item = by_index.get(i, {})
        fb_debut, fb_climax = fallback_pairs[i] if i < len(fallback_pairs) else (0, 1)
        debut_rank = _resolve_realm_rank(item.get("realm_at_debut"), rank_map, level_names, registry)
        climax_rank = _resolve_realm_rank(item.get("realm_at_climax"), rank_map, level_names, registry)
        if debut_rank < 0:
            debut_rank = fb_debut
        if climax_rank < 0:
            climax_rank = fb_climax
        if climax_rank < debut_rank:
            climax_rank = max(debut_rank, fb_climax)
        debut_name = (item.get("realm_at_debut") or "").strip()
        climax_name = (item.get("realm_at_climax") or "").strip()
        if i > 0 and out:
            prev_climax_rank = out[-1].get("realm_at_climax_rank", -1)
            if climax_rank < prev_climax_rank and level_names:
                climax_rank = min(prev_climax_rank + 1, len(level_names) - 1)
                climax_name = ""

        boss_name = (item.get("boss_name") or item.get("name") or f"卷{i + 1}Boss").strip()
        out.append({
            "vol_index": i,
            "boss_name": boss_name,
            "faction": (item.get("faction") or "").strip(),
            "realm_at_debut": debut_name or (level_names[debut_rank] if debut_rank < len(level_names) else ""),
            "realm_at_climax": climax_name or (level_names[climax_rank] if climax_rank < len(level_names) else ""),
            "realm_at_debut_rank": debut_rank,
            "realm_at_climax_rank": climax_rank,
            "narrative_function": (item.get("narrative_function") or item.get("role_in_volume") or "")[:120],
            "boss_kind": (item.get("boss_kind") or "arc_boss").strip(),
        })
    return out


def format_ladder_summary(ladder: list[dict]) -> str:
    parts: list[str] = []
    for row in ladder:
        vi = int(row.get("vol_index", 0))
        name = row.get("boss_name", "?")
        debut = row.get("realm_at_debut", "?")
        climax = row.get("realm_at_climax", "?")
        parts.append(f"第{vi + 1}卷·{name}（{debut}→对决{climax}）")
    return " | ".join(parts)


def persist_ladder(
    svc: Any, project: Any, ctx: dict, raw_data: Any, n_volumes: int
) -> list[dict]:
    """归一化 roster → 落库 Project.extra → 写 ctx（供独立步骤与合并节点共用）。"""
    from sqlalchemy.orm.attributes import flag_modified

    ladder = normalize_antagonist_ladder(raw_data, ctx, n_volumes)
    try:
        base = project.extra if isinstance(project.extra, dict) else {}
        project.extra = {**base, LADDER_EXTRA_KEY: ladder}
        flag_modified(project, "extra")
        svc.db.commit()
    except Exception:
        logger.exception("antagonist_ladder 写库失败 project=%s", project.id)

    ctx[LADDER_EXTRA_KEY] = ladder
    ctx["antagonist_ladder_summary"] = format_ladder_summary(ladder)
    ctx["volume_boss_names"] = [
        row.get("boss_name") for row in ladder if row.get("boss_name")
    ]
    return ladder


def build_antagonist_ladder_prompt_block(ctx: dict, n_volumes: int) -> str:
    """Step 9 注入：卷级 Boss 只能从 roster 选取。"""
    ladder: list[dict] = list(ctx.get("antagonist_ladder") or [])
    if not ladder:
        return ""
    lines = [
        "\n【卷级对立面登记表 — volume_boss / volume_boss_realm 必须逐卷引用下列条目，禁止另起新名】",
    ]
    for row in ladder:
        vi = int(row.get("vol_index", 0))
        lines.append(
            f"  第{vi + 1}卷：boss={row.get('boss_name')} | "
            f"volume_boss_realm={row.get('realm_at_climax')} | "
            f"登场≈{row.get('realm_at_debut')} | {row.get('narrative_function', '')[:50]}"
        )
    lines.append(
        "⚠️ 每卷 JSON 的 volume_boss 必须与上表 boss 完全一致；"
        "volume_boss_realm 必须与「对决境界」完全一致。"
    )
    return "\n".join(lines) + "\n"


def build_characters_ladder_block(ctx: dict) -> str:
    """Step 5 注入：必须为 roster 每个 Boss 生成完整人物卡。"""
    ladder: list[dict] = list(ctx.get("antagonist_ladder") or [])
    if not ladder:
        return ""
    lines = [
        "\n【卷级对立面登记表 — 下列 Boss 必须各生成 1 条完整人物 JSON（name 不得改写）】",
    ]
    for row in ladder:
        vi = int(row.get("vol_index", 0))
        lines.append(
            f"  · {row.get('boss_name')}：role=antagonist，character_tier=arc，"
            f"primary_volume={vi + 1}，current_realm={row.get('realm_at_debut')}，"
            f"peak_realm={row.get('realm_at_climax')}，"
            f"功能={row.get('narrative_function', '')[:60]}"
        )
    lines.append(
        "⚠️ 上述 Boss 姓名/境界/卷号与登记表冲突视为失败；"
        "不要另造与登记表重名的不同写法。"
    )
    return "\n".join(lines) + "\n"


def ladder_entry_for_volume(ladder: list[dict], vol_index: int) -> dict | None:
    for row in ladder:
        if int(row.get("vol_index", -1)) == vol_index:
            return row
    return ladder[vol_index] if 0 <= vol_index < len(ladder) else None


def bind_volume_boss_from_roster(
    vol_index: int,
    vol: dict,
    vol_extra: dict,
    ctx: dict,
) -> None:
    """落库时强制 volume_boss / volume_boss_realm 对齐 roster。"""
    ladder: list[dict] = list(ctx.get("antagonist_ladder") or [])
    entry = ladder_entry_for_volume(ladder, vol_index)
    if not entry:
        return

    roster_name = (entry.get("boss_name") or "").strip()
    roster_realm = (entry.get("realm_at_climax") or "").strip()
    ai_boss = (vol.get("volume_boss") or vol.get("volume_antagonist") or "").strip()

    if ai_boss and roster_name and ai_boss != roster_name:
        logger.warning(
            "bootstrap.volumes 第%d卷 volume_boss AI=%s roster=%s，已强制对齐 roster",
            vol_index + 1, ai_boss, roster_name,
        )
    if roster_name:
        vol_extra["volume_boss"] = roster_name
    if roster_realm:
        vol_extra["volume_boss_realm"] = roster_realm

    char_map: dict = ctx.get("char_name_to_id") or {}
    cid = char_map.get(roster_name)
    if cid:
        vol_extra["volume_boss_character_id"] = cid


def apply_ladder_fields_to_character(char_extra: dict, entry: dict) -> None:
    """人物落库时写入 roster 关联字段。"""
    if not entry:
        return
    vi = int(entry.get("vol_index", 0))
    char_extra["primary_volume"] = vi + 1
    char_extra["peak_realm"] = entry.get("realm_at_climax")
    char_extra["peak_realm_rank"] = entry.get("realm_at_climax_rank")
    char_extra["from_antagonist_ladder"] = True


def ladder_entry_by_name(ctx: dict, name: str) -> dict | None:
    name = (name or "").strip()
    if not name:
        return None
    for row in ctx.get("antagonist_ladder") or []:
        if (row.get("boss_name") or "").strip() == name:
            return row
    return None


def ensure_ladder_characters(
    svc: Any,
    project: Any,
    ctx: dict,
    results: list,
) -> list:
    """AI 漏掉登记表 Boss 时，用 roster 兜底落库最小 arc 反派。"""
    from app.models import Character

    ladder: list[dict] = list(ctx.get("antagonist_ladder") or [])
    if not ladder:
        return results

    existing = {c.name for c in results if getattr(c, "name", None)}
    registry = ctx.get("power_level_registry") or {}
    added: list = []

    for entry in ladder:
        name = (entry.get("boss_name") or "").strip()
        if not name or name in existing:
            continue
        debut = entry.get("realm_at_debut") or ""
        if registry and debut:
            resolved = resolve_realm_in_registry(str(debut), registry)
            if resolved:
                debut = resolved
        char_extra: dict = {}
        apply_ladder_fields_to_character(char_extra, entry)
        c = Character(
            project_id=project.id,
            name=name,
            role="antagonist",
            character_tier="arc",
            faction=(entry.get("faction") or None),
            motivation=(entry.get("narrative_function") or "")[:200] or None,
            current_realm=debut or None,
            extra=char_extra,
        )
        svc.db.add(c)
        results.append(c)
        existing.add(name)
        added.append(name)
        logger.warning(
            "characters: roster Boss「%s」未出现在 AI 输出，已代码兜底建档 project=%s",
            name, project.id,
        )

    if added:
        svc.db.flush()
    return results


def lint_antagonist_roster_issues(
    db: Any,
    project_id: Any,
    ctx: dict,
) -> list[dict]:
    """volume_boss ↔ Character ↔ roster 三角校验。"""
    from app.models import Character, OutlineNode

    issues: list[dict] = []
    ladder: list[dict] = list(ctx.get("antagonist_ladder") or [])
    if not ladder:
        from app.models import Project as _Project
        proj = db.query(_Project).filter(_Project.id == project_id).first()
        if proj and isinstance(proj.extra, dict):
            ladder = proj.extra.get(LADDER_EXTRA_KEY) or []
    if not ladder:
        return issues

    level_names: list[str] = list(ctx.get("power_level_names") or [])
    rank_map = {name: i for i, name in enumerate(level_names)}
    registry: dict = ctx.get("power_level_registry") or {}

    chars = db.query(Character).filter(Character.project_id == project_id).all()
    char_by_name = {c.name: c for c in chars if c.name}

    volumes = (
        db.query(OutlineNode)
        .filter(OutlineNode.project_id == project_id, OutlineNode.node_type == "volume")
        .order_by(OutlineNode.sort_order)
        .all()
    )

    roster_by_vol = {int(r.get("vol_index", -1)): r for r in ladder}

    for vol in volumes:
        vi = int(vol.sort_order or 0)
        extra = vol.extra if isinstance(vol.extra, dict) else {}
        boss = (extra.get("volume_boss") or "").strip()
        boss_realm = (extra.get("volume_boss_realm") or "").strip()
        roster = roster_by_vol.get(vi)
        if not roster:
            continue

        expected_name = (roster.get("boss_name") or "").strip()
        expected_realm = (roster.get("realm_at_climax") or "").strip()

        if expected_name and boss != expected_name:
            issues.append({
                "severity": "high",
                "type": "protagonist_alignment",
                "description": (
                    f"第{vi + 1}卷 volume_boss「{boss or '（空）'}」"
                    f"与对立面登记表「{expected_name}」不一致"
                ),
                "suggestion": f"将 volume_boss 改为「{expected_name}」",
                "auto_detected": True,
            })

        if expected_realm and boss_realm and boss_realm != expected_realm:
            issues.append({
                "severity": "high",
                "type": "realm_mismatch",
                "description": (
                    f"第{vi + 1}卷 Boss 境界「{boss_realm}」"
                    f"与登记表对决境界「{expected_realm}」不一致"
                ),
                "suggestion": f"将 volume_boss_realm 改为「{expected_realm}」",
                "auto_detected": True,
            })

        if expected_name and expected_name not in char_by_name:
            issues.append({
                "severity": "high",
                "type": "protagonist_alignment",
                "description": f"对立面「{expected_name}」未在人物库建档",
                "suggestion": f"在 Step 5 为「{expected_name}」生成 character_tier=arc 的反派档案",
                "auto_detected": True,
            })
            continue

        char = char_by_name[expected_name]
        from app.services.bootstrap.character_planning import (
            planning_peak_realm,
            realms_equivalent,
        )

        peak = planning_peak_realm(char)
        if not peak:
            issues.append({
                "severity": "medium",
                "type": "planning_gap",
                "description": (
                    f"arc Boss「{expected_name}」缺少 peak_realm（规划对决境），"
                    f"无法与第{vi + 1}卷登记表「{expected_realm}」对齐"
                ),
                "suggestion": f"在人物 extra.peak_realm 写入「{expected_realm}」",
                "auto_detected": True,
            })
            continue

        if expected_realm and not realms_equivalent(
            peak, expected_realm, level_names=level_names, registry=registry,
        ):
            issues.append({
                "severity": "medium",
                "type": "realm_mismatch",
                "description": (
                    f"人物「{expected_name}」peak_realm「{peak}」"
                    f"与登记表对决境界「{expected_realm}」不一致"
                ),
                "suggestion": f"将人物 peak_realm 对齐为「{expected_realm}」",
                "auto_detected": True,
            })

    return issues
