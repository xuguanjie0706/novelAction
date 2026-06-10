"""dabai Step：金手指 + 境界主轴 + 境界预算契约（合并）。"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.models import Project
from app.services.bootstrap.cultivation_budget import contract_from_ctx
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts.dabai_prompts import build_golden_power_dabai_prompt
from app.services.bootstrap.steps.xianxia.cultivation_contract import gen_cultivation_contract
from app.services.llm_token_budgets import max_tokens_bootstrap_completion
from app.services.outline_planning import words_to_plan

logger = logging.getLogger(__name__)


async def gen_golden_power_dabai(svc: Any, project: Project, ctx: dict) -> dict:
    """先走 cultivation_contract 落境界轴，再 LLM 补金手指 JSON。"""
    await gen_cultivation_contract(svc, project, ctx)

    system, prompt = build_golden_power_dabai_prompt(ctx)
    raw = await svc._call_with_retry(
        system, prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.dabai_golden_power",
    )
    data = parse_json(raw)
    if not isinstance(data, dict):
        data = {}
    gf = data.get("golden_finger") or {}
    ctx["golden_finger"] = gf
    ctx["dabai_golden_finger"] = gf

    extra = dict(project.extra or {})
    extra["golden_finger"] = gf
    extra["dabai_golden_finger"] = gf
    extra["bootstrap_mode"] = "dabai"
    if ctx.get("benchmark"):
        extra["benchmark"] = ctx["benchmark"]
    project.extra = extra
    flag_modified(project, "extra")
    svc.db.commit()

    tw = int(project.target_words or 1_200_000)
    n_volumes = words_to_plan(tw)["total_volumes"]
    contract = ctx.get("cultivation_contract") or contract_from_ctx(ctx, n_volumes)
    if contract:
        ctx["cultivation_contract"] = contract
        extra["cultivation_contract"] = contract
        project.extra = extra
        flag_modified(project, "extra")
        svc.db.commit()

    logger.info("dabai.golden_power project=%s gf=%s", project.id, gf.get("name"))
    return gf or {"name": "金手指"}
