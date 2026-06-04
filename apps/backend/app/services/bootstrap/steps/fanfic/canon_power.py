"""Bootstrap Fanfic：从原著提炼权力阶梯（不另造世界观）。"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.steps.fanfic._helpers import fanfic_meta_block, persist_extra
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


async def gen_canon_power(svc: Any, project: Project, ctx: dict) -> dict:
    system = "你是同人世界架构师。权力阶梯必须来自原著设定，禁止凭空新增大体系。只返回 JSON。"
    canon = ctx.get("fanfic_canon") or {}
    prompt = f"""{fanfic_meta_block(ctx)}
原著力量体系：{canon.get('power_system_from_source', '')}
创意：{ctx['logline']}

返回 JSON（与番茄 power_ladder 同结构，供下游复用）：
{{
  "world_core_rule": "支撑打脸的一条规则（20字内，须贴合原著）",
  "social_ladder": [
    {{"tier": 1, "name": "阶层名", "description": "...", "representative": "..."}},
    {{"tier": 2, "name": "...", "description": "...", "representative": "..."}},
    {{"tier": 3, "name": "...", "description": "...", "representative": "..."}},
    {{"tier": 4, "name": "...", "description": "...", "representative": "..."}},
    {{"tier": 5, "name": "...", "description": "...", "representative": "..."}}
  ],
  "protagonist_start_tier": 1,
  "protagonist_end_tier": 5,
  "wealth_visualization": "财富差距画面（一句话）",
  "power_visualization": "战力差距画面（一句话）",
  "setting_vibe": "氛围（10字内）",
  "canon_source_note": "与原著体系的对应说明（20字内）"
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
        if not isinstance(data, dict):
            last_err = "须为 JSON 对象"
            continue
        ladder = data.get("social_ladder")
        if not isinstance(ladder, list) or len(ladder) < 3:
            last_err = "social_ladder 至少 3 层"
            continue
        persist_extra(project, svc, "power_ladder", data)
        ctx["power_ladder"] = data
        return data
    return {}
