"""Bootstrap Fanfic：魔改边界契约。"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.steps.fanfic._helpers import fanfic_meta_block, persist_extra
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


async def gen_deviation_contract(svc: Any, project: Project, ctx: dict) -> dict:
    system = "你是同人编剧。明确「能改什么、不能改什么」，避免原著粉弃书。只返回 JSON。"
    dev = ctx.get("fanfic_deviation") or {}
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

    last_err = ""
    for attempt in range(3):
        fix = f"\n【请修正：{last_err}】" if last_err else ""
        raw = await svc._call_with_retry(
            system, prompt + fix,
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.positioning",
        )
        try:
            data = parse_json(raw)
        except Exception:
            last_err = "JSON 解析失败"
            continue
        if not isinstance(data, dict) or not data.get("divergence_point"):
            last_err = "divergence_point 必填"
            continue
        persist_extra(project, svc, "fanfic_deviation", data)
        ctx["fanfic_deviation"] = data
        return data
    # 三次仍失败：返回空 dict，让 _fanfic_step 判定为失败并触发 retry/interrupt，
    # 不把可能为空的旧 dev 当成功路径放给下游（避免下游拿到空契约继续跑）。
    return {}
