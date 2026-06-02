"""Step 2 力量曲线评委：独立 LLM 找茬 + 代码预检。"""

from __future__ import annotations

import json
from typing import Any

from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.steps.power_systems.invariants import _abilities_jaccard
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


def _code_critique_primary(systems: list) -> list[str]:
    """代码预检：质变注水、abilities 雷同（零 token）。"""
    issues: list[str] = []
    primary = next((s for s in systems if isinstance(s, dict) and s.get("axis_role") == "primary"), None)
    if not primary:
        return issues
    levels = [lv for lv in (primary.get("levels") or []) if isinstance(lv, dict)]
    for i in range(len(levels) - 2):
        leaps = [(levels[j].get("leap_type") or "") for j in range(i, i + 3)]
        if leaps[0] and leaps[0] == leaps[1] == leaps[2]:
            issues.append(f"主轴第{i + 1}~{i + 3} 层 leap_type 连续相同")
    for i in range(len(levels) - 1):
        if _abilities_jaccard(levels[i].get("abilities"), levels[i + 1].get("abilities")) > 0.85:
            n1 = levels[i].get("name") or f"第{i + 1}层"
            n2 = levels[i + 1].get("name") or f"第{i + 2}层"
            issues.append(f"主轴「{n1}」与「{n2}」abilities 过于雷同")
    return issues


async def run_power_curve_judge(svc: Any, bundle: dict[str, Any]) -> list[str]:
    """
    力量曲线评委：代码预检 + 独立 LLM 编辑找茬。

    @returns 问题列表；空列表表示通过
    """
    systems = bundle.get("systems") or []
    if not isinstance(systems, list):
        return ["systems 无效"]

    code_issues = _code_critique_primary(systems)
    if len(code_issues) >= 3:
        return code_issues

    primary = next((s for s in systems if isinstance(s, dict) and s.get("axis_role") == "primary"), None)
    if not primary:
        return code_issues or ["缺少主轴"]

    compact_levels = []
    for lv in (primary.get("levels") or [])[:12]:
        if not isinstance(lv, dict):
            continue
        compact_levels.append({
            "rank": lv.get("rank"),
            "name": lv.get("name"),
            "leap_type": lv.get("leap_type"),
            "leap_description": lv.get("leap_description"),
            "abilities": (lv.get("abilities") or [])[:4],
        })

    system = (
        "你是仙侠设定编辑（只找茬，不是原作者）。"
        "只返回 JSON：{\"pass\": true/false, \"issues\": [\"...\"]}"
    )
    prompt = f"""审查以下修行主轴 levels，找出「量变注水」层（相邻层仅战力+1、无新玩法/新场景/新叙事权限）。

levels:
{json.dumps(compact_levels, ensure_ascii=False)}

否决标准：
1. 任一层 leap_description 空泛（如「更强」「灵气更浓」）
2. 读者无法用一句话说出这层比上层多能干什么
3. 缺少渡劫/心魔层却 claim 仙侠完整体

pass=true 仅当 issues 为空。最多 5 条 issues。只返回 JSON。"""

    try:
        raw = await svc._call_with_retry(
            system,
            prompt,
            max_tokens=max_tokens_bootstrap_completion(),
            task="quality.check",
        )
        data = parse_json(raw)
        if isinstance(data, dict):
            llm_issues = [str(x) for x in (data.get("issues") or []) if x]
            if data.get("pass") is True and not llm_issues:
                return code_issues
            return code_issues + llm_issues[:5]
    except Exception:
        pass

    return code_issues
