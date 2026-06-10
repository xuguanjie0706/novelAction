"""dabai Step：势力 + 人物 + 故事线 + 卷级对立面（一次 LLM）。"""
from __future__ import annotations

import logging
from typing import Any

from app.models import Character, Project, StoryLine
from app.services.bootstrap.antagonist_roster import ensure_ladder_characters, persist_ladder
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.steps.dabai.dabai_converge import (
    bind_ladder_boss_names_to_characters,
    coerce_dabai_ladder_raw,
    normalize_dabai_character_realm,
    normalize_dabai_character_role,
    sync_ctx_char_maps,
)
from app.services.bootstrap.prompts.dabai_prompts import build_cast_world_dabai_prompt
from app.services.bootstrap.steps.factions import persist_factions, set_faction_ctx
from app.services.llm_token_budgets import max_tokens_bootstrap_completion
from app.services.outline_planning import words_to_plan

logger = logging.getLogger(__name__)


def _persist_dabai_characters(svc: Any, project: Project, data: list, ctx: dict) -> list:
    results = []
    for i, c in enumerate(data or []):
        if not isinstance(c, dict) or not c.get("name"):
            continue
        known = {"name", "role", "tier", "start_realm", "persona", "function"}
        extra = {k: v for k, v in c.items() if k not in known}
        role_raw = c.get("role", "supporting")
        canon_role, role_label = normalize_dabai_character_role(str(role_raw))
        is_protagonist = canon_role == "protagonist"
        realm = normalize_dabai_character_realm(
            c.get("start_realm"), ctx, is_protagonist=is_protagonist,
        )
        tier = c.get("tier") or c.get("character_tier")
        ch = Character(
            project_id=project.id,
            name=c.get("name", ""),
            role=canon_role,
            character_tier=tier if tier in ("core", "arc", "plot", "background") else "core",
            current_realm=realm,
            personality=c.get("persona"),
            author_notes=c.get("function"),
            extra={
                **extra,
                **({"dabai_role_label": role_label} if role_label else {}),
                **({"dabai_tier": tier} if tier else {}),
            },
        )
        svc.db.add(ch)
        results.append(ch)
    svc.db.commit()
    return results


def _persist_dabai_storylines(svc: Any, project: Project, data: list) -> list:
    results = []
    for i, s in enumerate(data or []):
        if not isinstance(s, dict):
            continue
        sl = StoryLine(
            project_id=project.id,
            name=s.get("name", f"故事线{i + 1}"),
            line_type=s.get("type", "main"),
            description=s.get("summary"),
            sort_order=i,
        )
        svc.db.add(sl)
        results.append(sl)
    svc.db.commit()
    return results


async def gen_cast_world_dabai(svc: Any, project: Project, ctx: dict) -> list:
    tw = int(project.target_words or ctx.get("target_words") or 1_200_000)
    n_volumes = words_to_plan(tw)["total_volumes"]
    ctx["target_words"] = tw

    system, prompt = build_cast_world_dabai_prompt(ctx, n_volumes)
    raw = await svc._call_with_retry(
        system, prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.dabai_cast_world",
    )
    data = parse_json(raw)
    if not isinstance(data, dict):
        data = {}

    factions_data = data.get("factions") or []
    if factions_data:
        results = persist_factions(svc, project, factions_data)
        set_faction_ctx(ctx, results)
    else:
        from app.services.bootstrap.steps.factions import gen_factions
        results = await gen_factions(svc, project, ctx)

    char_rows = data.get("characters") or []
    chars = _persist_dabai_characters(svc, project, char_rows, ctx)

    sls = _persist_dabai_storylines(svc, project, data.get("storylines") or [])
    ctx["storylines"] = [{"name": s.name, "type": s.line_type} for s in sls]

    ladder_raw = coerce_dabai_ladder_raw(data.get("antagonist_ladder") or [])
    ladder_raw = bind_ladder_boss_names_to_characters(ladder_raw, char_rows)
    if ladder_raw:
        persist_ladder(svc, project, ctx, ladder_raw, n_volumes)
        chars = ensure_ladder_characters(svc, project, ctx, chars)
        svc.db.commit()
    else:
        from app.services.bootstrap.steps.antagonist_ladder import gen_antagonist_ladder
        await gen_antagonist_ladder(svc, project, ctx)
        chars = ensure_ladder_characters(svc, project, ctx, chars)
        svc.db.commit()

    sync_ctx_char_maps(ctx, chars)

    logger.info(
        "dabai.cast_world project=%s factions=%d chars=%d storylines=%d",
        project.id, len(results), len(chars), len(sls),
    )
    return results
