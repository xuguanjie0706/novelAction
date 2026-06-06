"""番茄·修仙线 Step：契约执行式卷生成（replaces 通用 volumes）。

与通用 ``gen_volumes`` 的唯一**本质**差异：境界进度由「境界预算契约」硬执行——
1. prompt 注入逐卷已锁定的境界窗口（``build_cultivation_budget_block``），
   并剥离通用线性进度块（见下方剥离说明），避免软/硬两套约束打架；
2. 落库后对主角境界字段做**确定性 clamp**（契约覆写，不信任 LLM 数字），
   BOSS 境界超卷上限则下调——这是「第一卷修满」无法发生的根本保证。

其余（卷数规划、导演单节拍、BOSS roster 绑定、章号起点、实体 lint）复用通用步骤
函数 ``_persist_volumes`` / ``run_volume_entity_lint``，避免重复实现与逻辑漂移。
红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.models import Project
from app.services.bootstrap.cultivation_budget import (
    boss_name_within_cap,
    build_cultivation_budget_block,
    clamp_volume_extra_to_contract,
    contract_from_ctx,
    validate_volumes_against_contract,
)
from app.services.bootstrap.fanqie_realm_policy import hydrate_fanqie_power_ctx
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts.volumes import build_volumes_prompt
from app.services.bootstrap.steps.volumes import _persist_volumes, run_volume_entity_lint
from app.services.llm_token_budgets import max_tokens_bootstrap_completion
from app.services.outline_planning import words_to_plan
from app.utils.writing_style import resolve_project_writing_style

logger = logging.getLogger(__name__)


def _load_contract(project: Project, ctx: dict, n_volumes: int) -> dict | None:
    """优先 ctx，其次 project.extra，最后即时装配（存量/重跑兜底）。"""
    contract = ctx.get("cultivation_contract")
    if not contract:
        contract = (project.extra or {}).get("cultivation_contract")
    if not contract:
        contract = contract_from_ctx(ctx, n_volumes)
    return contract


def _name_to_rank(ctx: dict) -> dict[str, int]:
    """大境名 → 1-based rank（用于 BOSS 境界上限判定）。"""
    registry = ctx.get("power_level_registry") or {}
    out: dict[str, int] = {}
    for name, meta in registry.items():
        if isinstance(meta, dict) and isinstance(meta.get("rank"), int) and meta["rank"] > 0:
            out[name] = int(meta["rank"])
    if not out:
        for i, name in enumerate(ctx.get("power_level_names") or []):
            out[name] = i + 1
    return out


def _enforce_contract(svc: Any, project: Project, results: list, ctx: dict, contract: dict) -> None:
    """对落库卷节点做契约 clamp（核心强制点），并断言校验。"""
    n2r = _name_to_rank(ctx)
    all_notes: list[str] = []
    for i, node in enumerate(results):
        extra = dict(node.extra or {})
        notes = clamp_volume_extra_to_contract(extra, i, contract)
        boss = (extra.get("volume_boss_realm") or "").strip()
        if boss:
            fixed, warn = boss_name_within_cap(boss, i, contract, n2r)
            if warn:
                extra["volume_boss_realm"] = fixed
                notes.append(warn)
        if notes:
            node.extra = extra
            flag_modified(node, "extra")
            all_notes.extend(f"[卷{i + 1}] {x}" for x in notes)
    if all_notes:
        svc.db.commit()
        logger.warning(
            "xianxia.volumes 契约强制纠正 project=%s 共%d项: %s",
            project.id, len(all_notes), "; ".join(all_notes[:20]),
        )
    issues = validate_volumes_against_contract(
        [dict(n.extra or {}) for n in results], contract,
    )
    if issues:
        logger.error("xianxia.volumes 契约校验仍异常 project=%s: %s", project.id, issues)


async def gen_volumes_xianxia(svc: Any, project: Project, ctx: dict) -> list:
    """生成卷骨架并按境界预算契约硬执行。"""
    hydrate_fanqie_power_ctx(ctx)
    tw = int(project.target_words or 1_200_000)
    plan = words_to_plan(tw)
    n_volumes = plan["total_volumes"]
    contract = _load_contract(project, ctx, n_volumes)

    # 剥离说明：通用 build_volumes_prompt 无条件注入线性进度软约束块
    # （build_protagonist_progression_prompt_block 依赖 ctx['power_level_names']）。
    # 修仙线用契约硬约束块取而代之，故对传入 prompt 的 ctx **副本**剥离 power_level_names，
    # 使线性块返回空串；真实 ctx 不变，_persist_volumes 仍可正常读名。
    prompt_ctx = dict(ctx)
    prompt_ctx.pop("power_level_names", None)
    system, prompt_base = build_volumes_prompt(project, prompt_ctx)
    if resolve_project_writing_style(project) == "plain":
        system += (
            "\n\n【白话直白模式（番茄修仙纯爽文，卷骨架层）】"
            "beat_highlights 燃点与 volume_climax 高潮一律大白话直给——"
            "写清「谁、和谁、为什么冲突、爽在哪」，禁止含蓄留白或意境化辞藻。"
        )
    prompt = prompt_base + build_cultivation_budget_block(contract)

    raw = ""
    try:
        raw = await svc._call_with_retry(
            system, prompt,
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.volumes",
        )
        data = parse_json(raw)
    except Exception as exc:
        logger.error(
            "xianxia.volumes JSON 解析失败 project=%s: %s raw_tail=%r",
            project.id, exc, (raw or "")[-400:],
        )
        raise
    if not isinstance(data, list):
        data = data.get("outline", data.get("volumes", []))

    results = _persist_volumes(svc, project, data, ctx, n_volumes)

    if contract:
        _enforce_contract(svc, project, results, ctx, contract)

    run_volume_entity_lint(svc.db, project.id, ctx)
    ctx["volumes_summary"] = " | ".join(
        f"{n.title}：{(n.summary or '')[:40]}" for n in results
    )
    ctx["chapter_quota_total"] = plan["total_chapters"]
    ctx["chapter_quota_total_volumes"] = plan["total_volumes"]
    ctx["chapter_quota_used"] = 0
    logger.info(
        "xianxia.volumes 完成 project=%s 卷数=%d phases=%s",
        project.id, len(results), [getattr(n, "phase", None) for n in results],
    )
    return results
