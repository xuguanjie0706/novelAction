"""dabai Step：卷骨架 + 卷级地图 + 境界区间（一次 LLM + 契约 clamp）。"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.models import Location, OutlineNode, Project
from app.services.bootstrap.antagonist_roster import (
    bind_volume_boss_from_roster,
    build_antagonist_ladder_prompt_block,
)
from app.services.bootstrap.cultivation_budget import (
    build_cultivation_budget_block,
    clamp_volume_extra_to_contract,
    contract_from_ctx,
    validate_volumes_against_contract,
)
from app.services.bootstrap.fanqie_realm_policy import hydrate_fanqie_power_ctx
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts.dabai_prompts import build_volumes_map_dabai_prompt
from app.services.bootstrap.steps.volumes import run_volume_entity_lint
from app.services.bootstrap.steps.xianxia.volumes_xianxia import _enforce_contract, _load_contract
from app.services.bootstrap.volume_beats import apply_volume_beat_fields
from app.services.bootstrap.volume_chapter_starts import compute_chapter_starts
from app.services.llm_token_budgets import max_tokens_bootstrap_completion
from app.services.outline_planning import words_to_plan

logger = logging.getLogger(__name__)

_VALID_PHASES = frozenset({"opening", "rising", "turning", "dark_hour", "climax", "ending"})


def _persist_locations(svc: Any, project: Project, vol_num: int, world_map: dict) -> None:
    """把卷级地图地点写入 Location 表（按卷 sort_order 偏移）。"""
    base = (vol_num - 1) * 100
    for i, loc in enumerate(world_map.get("locations") or []):
        if not isinstance(loc, dict) or not loc.get("name"):
            continue
        danger = (loc.get("danger") or "neutral").lower()
        if danger not in ("safe", "neutral", "dangerous", "forbidden"):
            danger = "neutral"
        ltype = (loc.get("type") or "outdoor").lower()
        svc.db.add(Location(
            project_id=project.id,
            name=loc["name"].strip(),
            location_type=ltype if ltype in (
                "indoor", "outdoor", "ruins", "battlefield", "wilderness",
                "sacred_ground", "city", "dungeon", "void",
            ) else "outdoor",
            danger_level=danger,
            controller=(loc.get("controller") or "")[:100] or None,
            description=(world_map.get("map_note") or "")[:500] or None,
            sort_order=base + i,
            extra={"dabai_volume": vol_num, "travel_spine": world_map.get("travel_spine")},
        ))


def _persist_dabai_volumes(
    svc: Any, project: Project, data: list, ctx: dict, n_volumes: int,
) -> list:
    planned_list = []
    for vol in data:
        planned = vol.get("planned_chapters", 30)
        if not isinstance(planned, int) or planned < 15:
            planned = 30
        elif planned > 80:
            planned = 60
        planned_list.append(planned)
    chapter_starts = compute_chapter_starts(planned_list)
    results = []
    for i, vol in enumerate(data):
        planned = planned_list[i] if i < len(planned_list) else 30
        phase_val = (vol.get("phase") or "").strip().lower() or None
        if phase_val not in _VALID_PHASES:
            phase_val = "opening" if i == 0 else ("ending" if i == n_volumes - 1 else "rising")
        world_map = vol.get("world_map") if isinstance(vol.get("world_map"), dict) else {}
        vol_extra: dict = {
            "planned_chapters": planned,
            "phase": phase_val,
            "chapter_start_global": chapter_starts[i] if i < len(chapter_starts) else 1,
            "realm_start_rank": vol.get("realm_start_rank"),
            "realm_end_rank": vol.get("realm_end_rank"),
            "world_map": world_map,
            "big_beats": vol.get("big_beats") or [],
            "volume_climax": vol.get("volume_climax"),
            "end_hook": vol.get("end_hook"),
            "bootstrap_mode": "dabai",
        }
        bind_volume_boss_from_roster(i, vol, vol_extra, ctx)
        highlight_text = apply_volume_beat_fields(vol, vol_extra)
        node = OutlineNode(
            project_id=project.id,
            parent_id=None,
            node_type="volume",
            title=vol.get("title", f"第{i + 1}卷"),
            summary=vol.get("summary") or vol.get("volume_climax"),
            hook=vol.get("end_hook") or vol.get("hook"),
            sort_order=i,
            phase=phase_val,
            highlight=highlight_text,
            extra=vol_extra,
        )
        svc.db.add(node)
        results.append(node)
        if world_map:
            _persist_locations(svc, project, i + 1, world_map)
    svc.db.commit()
    return results


async def gen_volumes_map_dabai(svc: Any, project: Project, ctx: dict) -> list:
    hydrate_fanqie_power_ctx(ctx)
    tw = int(project.target_words or 1_200_000)
    plan = words_to_plan(tw)
    n_volumes = plan["total_volumes"]
    planned = plan.get("chapters_per_volume") or 30
    contract = _load_contract(project, ctx, n_volumes)

    system, prompt = build_volumes_map_dabai_prompt(ctx, n_volumes, planned)
    prompt += build_antagonist_ladder_prompt_block(ctx, n_volumes)
    if contract:
        prompt += build_cultivation_budget_block(contract)

    raw = await svc._call_with_retry(
        system, prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.dabai_volumes_map",
    )
    data = parse_json(raw)
    if not isinstance(data, list):
        data = data.get("volumes", data.get("outline", []))

    results = _persist_dabai_volumes(svc, project, data, ctx, n_volumes)

    if contract:
        _enforce_contract(svc, project, results, ctx, contract)
        for i, node in enumerate(results):
            extra = dict(node.extra or {})
            notes = clamp_volume_extra_to_contract(extra, i, contract)
            if notes:
                node.extra = extra
                flag_modified(node, "extra")
        svc.db.commit()
        issues = validate_volumes_against_contract(
            [dict(n.extra or {}) for n in results], contract,
        )
        if issues:
            logger.warning("dabai.volumes_map 契约校验 project=%s: %s", project.id, issues)

    run_volume_entity_lint(svc.db, project.id, ctx)
    ctx["volumes_summary"] = " | ".join(f"{n.title}" for n in results)
    ctx["chapter_quota_total"] = plan["total_chapters"]
    logger.info("dabai.volumes_map 完成 project=%s 卷数=%d", project.id, len(results))
    return results
