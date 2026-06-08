"""斗破线合并步骤：势力 + 卷级对立面 roster 一次 LLM 生成（replaces factions，吞 antagonist_ladder）。

为什么从「势力+功法+法宝三合一」改成这个
------------------------------------------
功法/法宝要**精确挂到人物 UUID**（mastered_by_character_ids / current_owner_id），就必须在
人物建档**之后**生成（那时 ctx 才有 char_id_list / char_name_to_id，落库层还能按境界过滤）。
而人物建档又依赖势力（faction_id）与卷级对立面（Boss roster），势力/对立面必须在人物**之前**。
一个节点无法同时满足两个相反位置，故拆分为：
  - 本步骤：势力 + 对立面 一次 LLM（人物前）——Boss 与势力同份 JSON 共生，不脱节；
  - 通用 CORE ``skills_items``：功法 + 法宝 一次 LLM（人物后）——精确挂 UUID + 按境界择人。

复用通用合并 prompt（``build_factions_antagonist_prompt``，本身题材中立、吃斗气主轴），
仅追加斗破「禁修仙 / 禁上帝视角 / 白话」铁律。落库复用 persist_factions / persist_ladder。
缺失部分回退对应独立步骤。红线：本文件 ≤ 600 行。
"""

from __future__ import annotations

import logging
from typing import Any

from app.models import Project
from app.services.bootstrap.antagonist_roster import persist_ladder
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts.doupo_prompts import NO_GOD_VIEW_RULE
from app.services.bootstrap.prompts.factions_antagonist import (
    build_factions_antagonist_prompt,
    split_factions_antagonist_payload,
)
from app.services.bootstrap.steps.factions import persist_factions, set_faction_ctx
from app.services.llm_token_budgets import max_tokens_bootstrap_completion
from app.services.outline_planning import words_to_plan

logger = logging.getLogger(__name__)


async def gen_factions_antagonist_doupo(svc: Any, project: Project, ctx: dict) -> list:
    """一次生成势力 + 卷级对立面，分别落库；缺失部分回退独立步骤。

    @returns Faction 列表（供薄壳判定 ok / count）。
    """
    tw = int(project.target_words or ctx.get("target_words") or 1_200_000)
    n_volumes = words_to_plan(tw)["total_volumes"]
    ctx["target_words"] = tw

    system, prompt = build_factions_antagonist_prompt(ctx, n_volumes)
    # 斗破风味注入：势力定位与 Boss 设计也走斗气大陆口吻、禁修仙、禁上帝视角、白话直给
    prompt = (
        f"{prompt}\n\n{NO_GOD_VIEW_RULE}\n"
        "【斗破势力/对立面附加约束】势力是斗气大陆的家族/学院/宗门/魂殿类组织；"
        "强弱一律用斗气阶位描述（如：坐镇一名斗宗），禁用修仙境界；每卷 Boss 的斗气阶位"
        "随卷递增成阶梯，主角靠成长去够。"
    )
    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.factions_antagonist",
    )
    factions_data, ladder_data = split_factions_antagonist_payload(parse_json(raw))

    # ── A. 势力落库（缺失则回退独立步骤）────────────────────────────────────
    if factions_data:
        results = persist_factions(svc, project, factions_data)
        set_faction_ctx(ctx, results)
    else:
        logger.warning("doupo.factions_antagonist 缺 factions，回退独立步骤 project=%s", project.id)
        from app.services.bootstrap.steps.factions import gen_factions
        results = await gen_factions(svc, project, ctx)

    # ── B. 卷级对立面落库（缺失则回退独立步骤）──────────────────────────────
    if ladder_data:
        persist_ladder(svc, project, ctx, ladder_data, n_volumes)
    else:
        logger.warning("doupo.factions_antagonist 缺 antagonist_ladder，回退独立步骤 project=%s", project.id)
        from app.services.bootstrap.steps.antagonist_ladder import gen_antagonist_ladder
        await gen_antagonist_ladder(svc, project, ctx)

    logger.info(
        "doupo.factions_antagonist 完成 project=%s 势力=%d 卷数=%d bosses=%s",
        project.id, len(results), n_volumes, ctx.get("volume_boss_names"),
    )
    return results
