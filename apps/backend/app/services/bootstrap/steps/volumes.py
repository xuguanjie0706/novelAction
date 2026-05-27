"""Bootstrap Step 9：卷级骨架。"""

from __future__ import annotations

import logging
from typing import Any

from app.models import OutlineNode, Project
from app.services.bootstrap.prompts.volumes import build_volumes_prompt
from app.services.bootstrap.protagonist_progression import apply_volume_protagonist_fields
from app.services.bootstrap.antagonist_roster import bind_volume_boss_from_roster
from app.services.bootstrap.volume_beats import apply_volume_beat_fields
from app.services.bootstrap.volume_entity_registry import (
    format_volume_realm_fix_hint,
    lint_volume_entity_issues,
)
from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion
from app.services.outline_planning import words_to_plan

logger = logging.getLogger(__name__)

_MAX_VOLUME_REALM_RETRIES = 2


def _persist_volumes(svc: Any, project: Project, data: list, ctx: dict, n_volumes: int) -> list:
    """将 AI 卷级 JSON 落库为 OutlineNode（volume）。"""
    valid_phases = {"opening", "rising", "turning", "dark_hour", "climax", "ending"}
    results = []
    for i, vol in enumerate(data):
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
        vol_extra: dict = {"planned_chapters": planned, "phase": phase_val}
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


def _wipe_volumes(svc: Any, project_id: Any) -> None:
    svc.db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "volume",
    ).delete(synchronize_session=False)
    svc.db.commit()


async def gen_volumes(svc: Any, project: Project, ctx: dict):
    """Bootstrap 阶段只生成卷级骨架（volume），不生成 chapter_plan。"""
    system, prompt_base = build_volumes_prompt(project, ctx)
    tw = int(project.target_words or 1_200_000)
    plan = words_to_plan(tw)
    n_volumes = plan["total_volumes"]

    fix_hint = ""
    data: list = []
    results: list = []

    for attempt in range(_MAX_VOLUME_REALM_RETRIES + 1):
        prompt = prompt_base + fix_hint
        logger.info(
            "bootstrap.volumes 开始 project=%s 期望卷数=%d target_words=%d attempt=%d",
            project.id,
            n_volumes,
            tw,
            attempt + 1,
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

        if attempt > 0:
            _wipe_volumes(svc, project.id)
        results = _persist_volumes(svc, project, data, ctx, n_volumes)

        try:
            vol_lint = lint_volume_entity_issues(svc.db, project.id, ctx)
        except Exception:
            logger.exception("bootstrap.volumes 实体校验跳过 project=%s", project.id)
            vol_lint = []

        high_realm = [
            i for i in vol_lint
            if i.get("severity") == "high"
            and i.get("type") in (
                "villain_alignment",
                "realm_mismatch",
                "path_alignment",
                "protagonist_alignment",
            )
        ]
        if high_realm and attempt < _MAX_VOLUME_REALM_RETRIES:
            fix_hint = format_volume_realm_fix_hint(high_realm)
            logger.warning(
                "bootstrap.volumes 战力曲线错误，定向重试 project=%s attempt=%d issues=%d",
                project.id,
                attempt + 1,
                len(high_realm),
            )
            continue

        if vol_lint:
            ctx["volume_entity_lint"] = vol_lint
            if high_realm:
                logger.warning(
                    "bootstrap.volumes 战力曲线仍有问题（已达重试上限）project=%s issues=%d",
                    project.id,
                    len(high_realm),
                )
            else:
                logger.warning(
                    "bootstrap.volumes 实体校验发现 %d 项 project=%s",
                    len(vol_lint),
                    project.id,
                )
        break

    logger.info(
        "bootstrap.volumes 完成 project=%s 写入卷数=%d phases=%s",
        project.id,
        len(results),
        [n.phase for n in results],
    )
    ctx["volumes_summary"] = " | ".join(
        f"{n.title}：{(n.summary or '')[:40]}" for n in results
    )

    # ── 全书章节配额计数器（在此初始化，供 vol*_chapter_plans 累计使用）────
    # 以 target_words 为单一数据源，与卷级 planned_chapters 之和保持一致
    plan = words_to_plan(tw)
    ctx["chapter_quota_total"] = plan["total_chapters"]
    ctx["chapter_quota_total_volumes"] = plan["total_volumes"]
    ctx["chapter_quota_used"] = 0  # 每次懒展开章纲后累加，防止跨卷漂移

    return results
