"""dabai Step 0：对标 + 立项（一次 LLM）。"""
from __future__ import annotations

from typing import Any

from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts.dabai_prompts import (
    build_positioning_dabai_prompt,
    dabai_to_generic_positioning,
)
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

to_generic_positioning = dabai_to_generic_positioning


async def gen_dabai_positioning(svc: Any, ctx: dict) -> dict:
    system, prompt = build_positioning_dabai_prompt(
        logline=ctx.get("logline", ""),
        premise=ctx.get("premise", ""),
    )
    raw = await svc._call_with_retry(
        system, prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.dabai_positioning",
    )
    data = parse_json(raw)
    if not isinstance(data, dict):
        data = {}
    benchmark = data.get("benchmark") or {}
    positioning = dabai_to_generic_positioning(
        data.get("positioning") or {},
        benchmark=benchmark,
    )
    positioning["bootstrap_mode"] = "dabai"
    ctx["benchmark"] = benchmark
    ctx["dabai_positioning"] = positioning
    ctx["positioning"] = positioning
    return positioning
