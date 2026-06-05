"""Bootstrap Fanfic：从原著提炼权力阶梯（不另造世界观）。"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.json_once import call_bootstrap_json_once
from app.services.bootstrap.steps.fanfic._helpers import fanfic_meta_block, persist_extra

_STEP = "fanfic_canon_power"


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

    def _validate(data: Any) -> str | None:
        if not isinstance(data, dict):
            return "须为 JSON 对象"
        ladder = data.get("social_ladder")
        if not isinstance(ladder, list) or len(ladder) < 3:
            return "social_ladder 至少 3 层"
        return None

    data = await call_bootstrap_json_once(
        svc,
        step=_STEP,
        system=system,
        prompt=prompt,
        task="bootstrap.positioning",
        validate=_validate,
    )
    persist_extra(project, svc, "power_ladder", data)
    ctx["power_ladder"] = data
    return data
