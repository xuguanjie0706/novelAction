"""Bootstrap Step 2：境界体系（修仙多轴 + 旧题材兼容）。"""

from __future__ import annotations

import logging
from typing import Any

from app.models import Project
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.steps.power_systems.architect import build_power_architecture
from app.services.bootstrap.steps.power_systems.invariants import apply_auto_fixes, validate_xianxia_bundle
from app.services.bootstrap.steps.power_systems.judge import run_power_curve_judge
from app.services.bootstrap.steps.power_systems.persist import (
    persist_legacy_systems,
    persist_xianxia_bundle,
    sync_ctx_after_persist,
)
from app.services.bootstrap.steps.power_systems.prompts import build_legacy_power_prompt, build_xianxia_power_prompt
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

logger = logging.getLogger(__name__)


async def _gen_xianxia_bundle(svc: Any, ctx: dict, arch: dict) -> dict:
    """多轴修仙：生成 → 自动修复 → 校验 → 最多 2 轮 revise。"""
    system = "你是修仙世界观总架构师。只返回 JSON 对象，不要解释文字。"
    prompt = build_xianxia_power_prompt(ctx, arch)
    last_errors: list[str] = []

    for attempt in range(3):
        fix = ""
        if last_errors:
            fix = "\n【请修正以下问题后重新输出完整 JSON】\n- " + "\n- ".join(last_errors)
        raw = await svc._call_with_retry(
            system,
            prompt + fix,
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.power_systems",
        )
        data = parse_json(raw)
        if isinstance(data, list):
            data = {"systems": data, "cultivation_laws": arch.get("cultivation_laws_template") or {}}
        if not isinstance(data, dict):
            last_errors = ["根须为 JSON 对象"]
            continue

        apply_auto_fixes(data, arch)
        last_errors = validate_xianxia_bundle(data, arch)
        if last_errors:
            logger.warning("xianxia power_systems attempt %s invariant errors: %s", attempt + 1, last_errors)
            continue

        judge_issues = await run_power_curve_judge(svc, data)
        if judge_issues:
            last_errors = judge_issues
            logger.warning("xianxia power_systems attempt %s judge issues: %s", attempt + 1, judge_issues)
            continue

        return data

    return data if isinstance(data, dict) else {}


async def gen_power_systems(svc: Any, project: Project, ctx: dict):
    """
    生成并落库境界体系。

    仙侠/玄幻：多轴 power bundle（primary + path + artifact + sect）。
    其它题材：legacy JSON 数组（向后兼容）。
    """
    arch = build_power_architecture(ctx)
    ctx["power_architecture"] = arch

    if arch.get("multi_axis"):
        bundle = await _gen_xianxia_bundle(svc, ctx, arch)
        results = persist_xianxia_bundle(svc, project, bundle)
    else:
        system = "你是网络小说世界构建专家。只返回JSON数组。"
        prompt = build_legacy_power_prompt(ctx)
        raw = await svc._call_with_retry(
            system,
            prompt,
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.power_systems",
        )
        data = parse_json(raw)
        if not isinstance(data, list):
            data = data.get("power_systems", []) if isinstance(data, dict) else []
        results = persist_legacy_systems(svc, project, data)

    sync_ctx_after_persist(ctx, project, results)
    return results
