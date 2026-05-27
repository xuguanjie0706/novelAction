"""战力时间轴：全员境界泳道数据构建。"""
from __future__ import annotations

from typing import Any

from app.models import Character
from app.services.bootstrap.antagonist_roster import load_antagonist_ladder
from app.services.bootstrap.realm_effective import effective_realm_score


def _lane_point(
    volume_order: int,
    realm_label: str,
    major_rank: int | None,
    *,
    slot: str,
) -> dict[str, Any] | None:
    if not realm_label or major_rank is None or major_rank < 0:
        return None
    return {
        "volume_order": volume_order,
        "realm_label": realm_label,
        "major_rank": major_rank,
        "effective_score": round(effective_realm_score(major_rank, realm_label), 2),
        "slot": slot,
    }


def build_character_realm_lanes(
    project: Any,
    characters: list[Character],
    rows: list[dict[str, Any]],
    name_to_rank: dict[str, int],
    rank_for_label,
) -> list[dict[str, Any]]:
    """
    为有人物境界锚点的角色生成泳道 segments。

    数据来源优先级：卷 extra 主角/Boss → antagonist_ladder → primary_volume/peak_realm → current_realm 末卷快照。
    """
    n_vol = len(rows)
    if n_vol < 1:
        return []

    ladder = load_antagonist_ladder(project)
    by_id = {str(c.id): c for c in characters}
    by_name = {c.name.strip(): c for c in characters if c.name}

    lane_map: dict[str, dict[str, Any]] = {}

    def ensure_lane(key: str, *, char: Character | None, display_name: str, role: str, tier: str) -> dict:
        if key not in lane_map:
            lane_map[key] = {
                "character_id": str(char.id) if char else None,
                "display_name": display_name,
                "role": role,
                "character_tier": tier,
                "segments": [],
            }
        return lane_map[key]

    # 主角 / Boss：来自卷级 rows
    for row in rows:
        vo = int(row["volume_order"])
        p_start = row.get("protagonist_realm_start") or ""
        p_end = row.get("protagonist_realm_end") or ""
        prs = row.get("protagonist_rank_start")
        pre = row.get("protagonist_rank_end")
        boss_realm = row.get("boss_realm") or ""
        boss_rank = row.get("boss_major_rank")
        boss_name = (row.get("boss_name") or "").strip()
        boss_cid = row.get("boss_character_id")

        protag = next((c for c in characters if getattr(c, "role", None) == "protagonist"), None)
        if protag:
            lane = ensure_lane(
                str(protag.id),
                char=protag,
                display_name=protag.name,
                role="protagonist",
                tier=getattr(protag, "character_tier", None) or "core",
            )
            for label, rank, slot in ((p_start, prs, "protagonist_start"), (p_end, pre, "protagonist_end")):
                pt = _lane_point(vo, str(label), rank, slot=slot)
                if pt:
                    lane["segments"].append(pt)

        boss_char = by_id.get(str(boss_cid)) if boss_cid else by_name.get(boss_name)
        lane_key = str(boss_char.id) if boss_char else f"boss:{boss_name}:{vo}"
        lane = ensure_lane(
            lane_key,
            char=boss_char,
            display_name=boss_name or (boss_char.name if boss_char else "卷Boss"),
            role=getattr(boss_char, "role", None) if boss_char else "antagonist",
            tier=getattr(boss_char, "character_tier", None) if boss_char else "arc",
        )
        pt = _lane_point(vo, boss_realm, boss_rank, slot="volume_boss")
        if pt:
            lane["segments"].append(pt)

    # roster 登场/卷末（补未写入 volume 行的 Boss）
    for entry in ladder:
        if not isinstance(entry, dict):
            continue
        vi = entry.get("vol_index")
        try:
            vo = int(vi) + 1
        except (TypeError, ValueError):
            continue
        if vo < 1 or vo > n_vol:
            continue
        boss_name = (entry.get("boss_name") or "").strip()
        if not boss_name:
            continue
        boss_char = by_name.get(boss_name)
        lane_key = str(boss_char.id) if boss_char else f"boss:{boss_name}"
        lane = ensure_lane(
            lane_key,
            char=boss_char,
            display_name=boss_name,
            role=getattr(boss_char, "role", None) if boss_char else "antagonist",
            tier=getattr(boss_char, "character_tier", None) if boss_char else "arc",
        )
        existing_vols = {s["volume_order"] for s in lane["segments"]}
        if vo in existing_vols:
            continue
        debut = (entry.get("realm_at_debut") or "").strip()
        climax = (entry.get("realm_at_climax") or "").strip()
        dr = rank_for_label(debut, name_to_rank)
        cr = rank_for_label(climax, name_to_rank)
        for label, rank, slot in ((debut, dr, "debut"), (climax, cr, "climax")):
            pt = _lane_point(vo, label, rank, slot=slot)
            if pt:
                lane["segments"].append(pt)

    # 人物卡 primary_volume / peak_realm
    for char in characters:
        extra = char.extra if isinstance(char.extra, dict) else {}
        pv = extra.get("primary_volume")
        try:
            vo = int(pv)
        except (TypeError, ValueError):
            vo = None
        if vo is None or vo < 1 or vo > n_vol:
            continue
        lane = ensure_lane(
            str(char.id),
            char=char,
            display_name=char.name,
            role=getattr(char, "role", None) or "supporting",
            tier=getattr(char, "character_tier", None) or "plot",
        )
        peak = (extra.get("peak_realm") or char.current_realm or "").strip()
        pr = extra.get("peak_realm_rank")
        if isinstance(pr, bool) or pr is None:
            pr = rank_for_label(peak, name_to_rank)
        else:
            try:
                pr = int(pr)
            except (TypeError, ValueError):
                pr = rank_for_label(peak, name_to_rank)
        pt = _lane_point(vo, peak, pr, slot="peak")
        if pt and not any(s["volume_order"] == vo and s["slot"] == "peak" for s in lane["segments"]):
            lane["segments"].append(pt)

    # 仅有 current_realm 的角色：末卷快照
    for char in characters:
        lane = lane_map.get(str(char.id))
        if lane and lane["segments"]:
            continue
        realm = (char.current_realm or "").strip()
        if not realm:
            continue
        rank = char.realm_rank if isinstance(char.realm_rank, int) else rank_for_label(realm, name_to_rank)
        lane = ensure_lane(
            str(char.id),
            char=char,
            display_name=char.name,
            role=getattr(char, "role", None) or "supporting",
            tier=getattr(char, "character_tier", None) or "background",
        )
        pt = _lane_point(n_vol, realm, rank, slot="current_snapshot")
        if pt:
            lane["segments"].append(pt)

    role_order = {"protagonist": 0, "antagonist": 1, "supporting": 2, "neutral": 3}
    tier_order = {"core": 0, "arc": 1, "plot": 2, "background": 3}

    lanes = list(lane_map.values())
    for lane in lanes:
        lane["segments"].sort(key=lambda s: (s["volume_order"], s["slot"]))

    lanes.sort(
        key=lambda ln: (
            role_order.get(ln.get("role") or "", 9),
            tier_order.get(ln.get("character_tier") or "", 9),
            ln.get("display_name") or "",
        )
    )
    return lanes
