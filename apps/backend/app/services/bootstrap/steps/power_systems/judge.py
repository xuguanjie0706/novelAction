"""Step 2 力量曲线评委：代码预检（Bootstrap 不调 LLM）。"""

from __future__ import annotations

from typing import Any

from app.services.bootstrap.steps.power_systems.invariants import _abilities_jaccard


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
    力量曲线评委：仅代码预检（Bootstrap 阶段不调 LLM 质检）。

    @returns 问题列表；空列表表示通过
    """
    systems = bundle.get("systems") or []
    if not isinstance(systems, list):
        return ["systems 无效"]

    return _code_critique_primary(systems)
