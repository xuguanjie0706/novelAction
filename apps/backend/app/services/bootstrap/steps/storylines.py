"""Bootstrap Step 4：故事线身份 + 织网矩阵（两次 LLM + Linter）。"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.models import Project, StoryLine
from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.power_registry import format_power_context_block
from app.services.bootstrap.prompts.storyline_weave import (
    build_storyline_identity_prompt,
    build_storyline_weave_prompt,
    default_volume_phases,
)
from app.services.bootstrap.storyline_linter import (
    has_blocking_issues,
    lint_storyline_weave,
    normalize_storyline_weights,
)
from app.services.llm_token_budgets import max_tokens_bootstrap_completion
from app.services.outline_planning import words_to_plan

logger = logging.getLogger(__name__)

_MAX_WEAVE_RETRIES = 2


def _parse_identity_list(raw: str) -> list[dict]:
    data = parse_json(raw)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        inner = data.get("storylines", data.get("lines", []))
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []


def _parse_weave_payload(raw: str) -> dict:
    data = parse_json(raw)
    if isinstance(data, dict):
        return data
    return {}


def _active_dormant_from_beats(beats: list[dict], n_volumes: int) -> tuple[list[int], list[int]]:
    active: list[int] = []
    dormant: list[int] = []
    for i in range(n_volumes):
        row = next((b for b in beats if int(b.get("vol_index", -1)) == i), None)
        if row and row.get("is_active", True):
            active.append(i)
        else:
            dormant.append(i)
    return active, dormant


def _tension_curve(beats: list[dict], n_volumes: int) -> list[int]:
    curve: list[int] = []
    for i in range(n_volumes):
        row = next((b for b in beats if int(b.get("vol_index", -1)) == i), None)
        curve.append(int((row or {}).get("tension") or 0))
    return curve


def _crossovers_for_line(name: str, all_crossovers: list) -> list[dict]:
    out: list[dict] = []
    for c in all_crossovers or []:
        if not isinstance(c, dict):
            continue
        la, lb = c.get("line_a"), c.get("line_b")
        if name in (la, lb):
            other = lb if la == name else la
            out.append({
                "with": other,
                "at_vol": c.get("at_vol"),
                "trigger": c.get("trigger"),
                "effect_on_both": c.get("effect_on_both"),
            })
    return out


def _persist_storylines(
    svc: Any,
    project: Project,
    identity_lines: list[dict],
    weave_payload: dict,
    n_volumes: int,
) -> list[StoryLine]:
    matrix = weave_payload.get("weave_matrix") or {}
    crossovers = weave_payload.get("crossover_nodes") or []
    results: list[StoryLine] = []

    for i, item in enumerate(identity_lines):
        name = item.get("name", f"故事线{i + 1}")
        beats = matrix.get(name) or []
        active_vols, dormant_vols = _active_dormant_from_beats(beats, n_volumes)
        extra = {
            "volume_beats": beats,
            "crossover_nodes": _crossovers_for_line(name, crossovers),
            "active_volumes": active_vols,
            "dormant_volumes": dormant_vols,
            "weight": float(item.get("weight") or 0),
            "tension_curve": _tension_curve(beats, n_volumes),
            "theme_link": item.get("theme_link"),
            "resolution_volume": item.get("resolution_volume_hint"),
            "related_character_names": item.get("related_character_names") or [],
            "actual_beats": [],
            "weave_version": 1,
        }
        start_ch = item.get("start_chapter")
        if active_vols:
            start_ch = start_ch or (active_vols[0] * 60 + 1)

        sl = StoryLine(
            project_id=project.id,
            name=name,
            line_type=item.get("line_type", "sub"),
            description=item.get("description"),
            core_conflict=item.get("core_conflict"),
            resolution_direction=item.get("resolution_direction"),
            status=item.get("status", "planned"),
            start_chapter=start_ch,
            sort_order=i,
            extra=extra,
        )
        svc.db.add(sl)
        results.append(sl)

    svc.db.commit()
    return results


def _format_weave_summary(lines: list[StoryLine], n_volumes: int) -> str:
    parts: list[str] = []
    for sl in lines:
        extra = sl.extra if isinstance(sl.extra, dict) else {}
        w = extra.get("weight", "")
        parts.append(f"{sl.name}（{sl.line_type}，权重{w}）")
    return " | ".join(parts) + f" [织网 {n_volumes} 卷]"


async def gen_storylines(svc: Any, project: Project, ctx: dict):
    """生成故事线身份并织网，落库 StoryLine.extra。"""
    kit_block = get_genre_kit_block(ctx)
    power_block = format_power_context_block(ctx)
    tw = int(project.target_words or ctx.get("target_words") or 1_200_000)
    plan = words_to_plan(tw)
    n_volumes = plan["total_volumes"]
    volume_phases = default_volume_phases(n_volumes)
    ctx["target_words"] = tw

    system_identity = "你是网络小说叙事结构专家。只返回 JSON 数组。"
    id_prompt = build_storyline_identity_prompt(ctx, kit_block, power_block)
    raw_id = await svc._call_with_retry(
        system_identity,
        id_prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.storylines",
    )
    identity_lines = _parse_identity_list(raw_id)
    if not identity_lines:
        raise ValueError("storylines 身份生成解析为空")

    identity_lines = normalize_storyline_weights(identity_lines)

    system_weave = (
        "你是有30年经验的网文总编辑，负责故事线织网规划。只返回 JSON 对象。"
    )
    weave_payload: dict = {}
    last_issues: list = []

    for attempt in range(_MAX_WEAVE_RETRIES + 1):
        weave_prompt = build_storyline_weave_prompt(
            ctx, identity_lines, n_volumes, volume_phases, kit_block,
        )
        raw_weave = await svc._call_with_retry(
            system_weave,
            weave_prompt,
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.storyline_weave",
        )
        weave_payload = _parse_weave_payload(raw_weave)
        last_issues = lint_storyline_weave(
            identity_lines, weave_payload, n_volumes, volume_phases,
        )
        if not has_blocking_issues(last_issues):
            break
        logger.warning(
            "storyline weave lint blocked attempt=%d project=%s issues=%s",
            attempt,
            project.id,
            [f"{i.rule_id}:{i.message}" for i in last_issues if i.severity == "BLOCK"],
        )

    for issue in last_issues:
        if issue.severity == "WARN":
            logger.info("storyline weave %s: %s", issue.rule_id, issue.message)

    results = _persist_storylines(svc, project, identity_lines, weave_payload, n_volumes)

    ctx["storyline_summary"] = _format_weave_summary(results, n_volumes)
    ctx["storyline_ids"] = {sl.name: str(sl.id) for sl in results}
    ctx["storyline_weave"] = {
        "n_volumes": n_volumes,
        "volume_phases": volume_phases,
        "weave_matrix": weave_payload.get("weave_matrix"),
        "crossover_nodes": weave_payload.get("crossover_nodes"),
    }

    try:
        base = project.extra if isinstance(project.extra, dict) else {}
        project.extra = {
            **base,
            "storyline_weave_meta": {
                "n_volumes": n_volumes,
                "lint_warnings": [
                    {"rule": i.rule_id, "msg": i.message}
                    for i in last_issues if i.severity == "WARN"
                ],
            },
        }
        flag_modified(project, "extra")
        svc.db.commit()
    except Exception:
        logger.exception("storyline_weave_meta 写库失败 project=%s", project.id)

    return results
