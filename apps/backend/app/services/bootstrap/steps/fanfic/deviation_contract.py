"""Bootstrap Fanfic：魔改边界契约。"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.json_once import call_bootstrap_json_once
from app.services.bootstrap.steps.fanfic._helpers import fanfic_meta_block, persist_extra

_STEP = "fanfic_deviation"


async def gen_deviation_contract(svc: Any, project: Project, ctx: dict) -> dict:
    system = "你是同人编剧。明确「能改什么、不能改什么」，避免原著粉弃书。只返回 JSON。"
    canon = ctx.get("fanfic_canon") or {}
    prompt = f"""{fanfic_meta_block(ctx)}
创意：{ctx['logline']}

不可改事实：
{'; '.join((canon.get('immutable_facts') or [])[:8])}

返回 JSON：
{{
  "divergence_point": "本书相对原著的第一处分歧点（何时/何地/何事，25字内）",
  "allowed_changes": ["允许改动 3-5 条"],
  "forbidden_changes": ["禁止改动 3-5 条，须具体"],
  "cp_promise": "感情线/CP承诺（无CP则写「无」）",
  "ooc_budget": "low|medium|high",
  "main_plot_promise": "本书主线相对原著的新增价值（30字内）"
}}"""

    def _validate(data: Any) -> str | None:
        if not isinstance(data, dict) or not data.get("divergence_point"):
            return "divergence_point 必填"
        return None

    data = await call_bootstrap_json_once(
        svc,
        step=_STEP,
        system=system,
        prompt=prompt,
        task="bootstrap.positioning",
        validate=_validate,
    )
    persist_extra(project, svc, "fanfic_deviation", data)
    ctx["fanfic_deviation"] = data
    return data
