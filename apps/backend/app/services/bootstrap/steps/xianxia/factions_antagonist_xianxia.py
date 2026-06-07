"""修仙线合并步骤：势力体系 + 卷级对立面 roster 一次 LLM 生成。

替代通用线的两个独立步骤（factions / antagonist_ladder），把它们并成一次调用：
- 省一次 LLM 调用；
- 势力与每卷 Boss 同一份 JSON 共生，Boss.faction 强制取自同一响应里的势力，
  从结构上消除"Boss 挂靠不存在势力"的设定冲突。

健壮性：若合并响应缺了某一部分，自动回退到对应的原始独立步骤补齐，保证不因合并而少产物。

红线：本文件 ≤ 600 行。
"""

from __future__ import annotations

import logging
from typing import Any

from app.models import Project
from app.services.bootstrap.antagonist_roster import persist_ladder
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts.factions_antagonist import (
    build_factions_antagonist_prompt,
    split_factions_antagonist_payload,
)
from app.services.bootstrap.steps.factions import (
    persist_factions,
    set_faction_ctx,
)
from app.services.llm_token_budgets import max_tokens_bootstrap_completion
from app.services.outline_planning import words_to_plan

logger = logging.getLogger(__name__)


async def gen_factions_antagonist_xianxia(
    svc: Any, project: Project, ctx: dict
) -> list:
    """一次生成势力 + 卷级对立面，分别落库；缺失部分回退原步骤。

    Returns:
        Faction 列表（供 _fanqie_step 判定 ok / count）。
    """
    tw = int(project.target_words or ctx.get("target_words") or 1_200_000)
    n_volumes = words_to_plan(tw)["total_volumes"]
    ctx["target_words"] = tw

    system, prompt = build_factions_antagonist_prompt(ctx, n_volumes)
    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.factions_antagonist",
    )
    factions_data, ladder_data = split_factions_antagonist_payload(parse_json(raw))

    # ── A. 势力落库（缺失则回退独立步骤）──────────────────────────────────────
    if factions_data:
        results = persist_factions(svc, project, factions_data)
        set_faction_ctx(ctx, results)
    else:
        logger.warning(
            "factions_antagonist 合并响应缺 factions，回退独立步骤 project=%s", project.id
        )
        from app.services.bootstrap.steps.factions import gen_factions
        results = await gen_factions(svc, project, ctx)

    # ── B. 卷级对立面落库（缺失则回退独立步骤）────────────────────────────────
    if ladder_data:
        persist_ladder(svc, project, ctx, ladder_data, n_volumes)
    else:
        logger.warning(
            "factions_antagonist 合并响应缺 antagonist_ladder，回退独立步骤 project=%s",
            project.id,
        )
        from app.services.bootstrap.steps.antagonist_ladder import gen_antagonist_ladder
        await gen_antagonist_ladder(svc, project, ctx)

    logger.info(
        "bootstrap.factions_antagonist 完成 project=%s 势力=%d 卷数=%d bosses=%s",
        project.id,
        len(results),
        n_volumes,
        ctx.get("volume_boss_names"),
    )
    return results
