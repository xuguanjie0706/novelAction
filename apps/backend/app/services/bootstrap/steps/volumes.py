"""Bootstrap Step 9：卷级骨架。"""

from __future__ import annotations

import logging
from typing import Any

from app.models import OutlineNode, Project
from app.services.bootstrap.prompts.volumes import build_volumes_prompt
from app.services.bootstrap.protagonist_progression import apply_volume_protagonist_fields
from app.services.bootstrap.antagonist_roster import bind_volume_boss_from_roster
from app.services.bootstrap.volume_beats import apply_volume_beat_fields
from app.services.bootstrap.volume_chapter_starts import compute_chapter_starts
from app.services.bootstrap.volume_entity_registry import (
    format_volume_realm_fix_hint,
    lint_volume_entity_issues,
)
from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion
from app.services.outline_planning import words_to_plan
from app.utils.writing_style import resolve_project_writing_style

logger = logging.getLogger(__name__)

_HIGH_REALM_ISSUE_TYPES = frozenset({
    "villain_alignment",
    "realm_mismatch",
    "path_alignment",
    "protagonist_alignment",
})


def _high_realm_issues(vol_lint: list) -> list:
    return [
        i for i in vol_lint
        if i.get("severity") == "high"
        and i.get("type") in _HIGH_REALM_ISSUE_TYPES
    ]


def realm_fix_hint_from_ctx(ctx: dict) -> str:
    """从 ctx 中上次 linter 结果提取战力修正提示（供手动重试注入）。"""
    vol_lint = ctx.get("volume_entity_lint") or []
    high = _high_realm_issues(vol_lint)
    return format_volume_realm_fix_hint(high) if high else ""


def run_volume_entity_lint(db: Any, project_id: Any, ctx: dict) -> list:
    """运行卷级实体校验；失败时返回空列表。"""
    try:
        return lint_volume_entity_issues(db, project_id, ctx)
    except Exception:
        logger.exception("bootstrap.volumes 实体校验跳过 project=%s", project_id)
        return []


def _persist_volumes(svc: Any, project: Project, data: list, ctx: dict, n_volumes: int) -> list:
    """将 AI 卷级 JSON 落库为 OutlineNode（volume）。"""
    valid_phases = {"opening", "rising", "turning", "dark_hour", "climax", "ending"}
    planned_list: list[int] = []
    for vol in data:
        planned = vol.get("planned_chapters", 30)
        if not isinstance(planned, int) or planned < 15:
            planned = 30
        elif planned > 80:
            logger.warning(
                "bootstrap.volumes planned_chapters=%d 超出合理区间（>80），修正为60 project=%s",
                planned,
                project.id,
            )
            planned = 60
        planned_list.append(planned)
    chapter_starts = compute_chapter_starts(planned_list)
    results = []
    for i, vol in enumerate(data):
        planned = planned_list[i]
        phase_val = (vol.get("phase") or "").strip().lower() or None
        if phase_val and phase_val not in valid_phases:
            phase_val = None
        if phase_val is None:
            total_hint = max(1, len(data))
            if i == 0:
                phase_val = "opening"
            elif i == total_hint - 1:
                phase_val = "ending"
            else:
                phase_val = "rising"
        vol_extra: dict = {
            "planned_chapters": planned,
            "phase": phase_val,
            "chapter_start_global": chapter_starts[i],
        }
        boss = (vol.get("volume_boss") or vol.get("volume_antagonist") or "").strip()
        boss_realm = (vol.get("volume_boss_realm") or "").strip()
        boss_path = (vol.get("volume_boss_path") or "").strip()
        boss_path_rank = (vol.get("volume_boss_path_rank") or "").strip()
        if boss:
            vol_extra["volume_boss"] = boss
        if boss_realm:
            vol_extra["volume_boss_realm"] = boss_realm
        if boss_path:
            vol_extra["volume_boss_path"] = boss_path
        if boss_path_rank:
            vol_extra["volume_boss_path_rank"] = boss_path_rank
        apply_volume_protagonist_fields(vol, vol_extra, i, ctx, n_volumes)
        bind_volume_boss_from_roster(i, vol, vol_extra, ctx)
        highlight_text = apply_volume_beat_fields(vol, vol_extra)
        node = OutlineNode(
            project_id=project.id,
            parent_id=None,
            node_type="volume",
            title=vol.get("title", f"第{i+1}卷"),
            summary=vol.get("summary"),
            hook=vol.get("hook"),
            conflict=vol.get("conflict"),
            highlight=highlight_text,
            sort_order=i,
            phase=phase_val,
            extra=vol_extra,
        )
        svc.db.add(node)
        results.append(node)
    svc.db.commit()
    return results


async def gen_volumes(
    svc: Any,
    project: Project,
    ctx: dict,
    *,
    inject_realm_fix_hint: bool = False,
):
    """Bootstrap 阶段只生成卷级骨架（volume），不生成 chapter_plan。

    自动模式仅调用 LLM 一次；战力曲线 high 级问题写入 ctx，由闸门/单步重跑时
    ``inject_realm_fix_hint=True`` 注入修正提示后再手动重试。
    """
    from app.services.bootstrap.fanqie_realm_policy import hydrate_fanqie_power_ctx

    hydrate_fanqie_power_ctx(ctx)
    system, prompt_base = build_volumes_prompt(project, ctx)
    # 白话直白（番茄纯爽文）：番茄线已改走本通用 Step 9 出卷骨架，卷级燃点/高潮描述
    # 也要为直白正文服务，避免在卷纲层就写得文绉绉，与章纲/正文的 plain 约束对齐。
    if resolve_project_writing_style(project) == "plain":
        system += (
            "\n\n【白话直白模式（番茄纯爽文，卷骨架层）】"
            "beat_highlights 燃点与 volume_climax 高潮一律用大白话直给——"
            "写清楚「谁、和谁、为什么冲突、爽在哪」，禁止含蓄留白或意境化辞藻；"
            "卷阶段节奏服务于一章一爽点的直白展开。"
        )
    tw = int(project.target_words or 1_200_000)
    plan = words_to_plan(tw)
    n_volumes = plan["total_volumes"]

    fix_hint = realm_fix_hint_from_ctx(ctx) if inject_realm_fix_hint else ""
    prompt = prompt_base + fix_hint
    logger.info(
        "bootstrap.volumes 开始 project=%s 期望卷数=%d target_words=%d manual_realm_fix=%s",
        project.id,
        n_volumes,
        tw,
        bool(fix_hint),
    )

    raw = ""
    try:
        raw = await svc._call_with_retry(
            system,
            prompt,
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.volumes",
        )
        data = parse_json(raw)
    except Exception as exc:
        logger.error(
            "bootstrap.volumes JSON 解析失败 project=%s: %s; raw_tail=%r",
            project.id,
            exc,
            (raw or "")[-500:],
        )
        raise
    if not isinstance(data, list):
        data = data.get("outline", data.get("volumes", []))
    if len(data) != n_volumes:
        logger.warning(
            "bootstrap.volumes 卷数漂移 project=%s 期望=%d 实际=%d",
            project.id,
            n_volumes,
            len(data),
        )

    results = _persist_volumes(svc, project, data, ctx, n_volumes)
    vol_lint = run_volume_entity_lint(svc.db, project.id, ctx)
    high_realm = _high_realm_issues(vol_lint)

    if vol_lint:
        ctx["volume_entity_lint"] = vol_lint
        if high_realm:
            logger.warning(
                "bootstrap.volumes 战力曲线问题（请手动重试修正）project=%s issues=%d",
                project.id,
                len(high_realm),
            )
        else:
            logger.warning(
                "bootstrap.volumes 实体校验发现 %d 项 project=%s",
                len(vol_lint),
                project.id,
            )

    logger.info(
        "bootstrap.volumes 完成 project=%s 写入卷数=%d phases=%s",
        project.id,
        len(results),
        [n.phase for n in results],
    )
    ctx["volumes_summary"] = " | ".join(
        f"{n.title}：{(n.summary or '')[:40]}" for n in results
    )

    plan = words_to_plan(tw)
    ctx["chapter_quota_total"] = plan["total_chapters"]
    ctx["chapter_quota_total_volumes"] = plan["total_volumes"]
    ctx["chapter_quota_used"] = 0

    return results
