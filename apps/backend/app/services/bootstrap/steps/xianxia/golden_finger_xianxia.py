"""修仙直白线 Step：金手指（咬合境界轴，replaces 番茄 fanqie_formula 的泛化信息差）。

依赖：须在 cultivation_axis（境界主轴）之后执行——金手指要引用真实境界轴名与阶梯，
确保金手指与数值体系咬合，而非番茄式『信息差/未卜先知』。
产物落 ``Project.extra['golden_finger']``（沿用通用键，下游 ctx/正文可读）+ ctx。
红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.models import Project
from app.services.bootstrap.json_once import call_bootstrap_json_once
from app.services.bootstrap.prompts.xianxia_golden_finger_prompt import (
    build_xianxia_golden_finger_prompt,
)


def _validate(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "须为 JSON 对象"
    for k in ("finger_name", "axis_coupling", "input_cost"):
        if not (data.get(k) or "").strip():
            return f"{k} 不能为空"
    return None


async def gen_golden_finger_xianxia(svc: Any, project: Project, ctx: dict) -> dict:
    """生成咬合境界轴的修仙金手指。

    @returns golden_finger dict
    @raises BootstrapStepError: JSON 解析或字段校验失败
    """
    xp = ctx.get("xianxia_positioning") or {}
    ladder = ctx.get("power_ladder") if isinstance(ctx.get("power_ladder"), dict) else {}
    level_names = list(ctx.get("power_level_names") or [])
    realm_axis_name = (ladder.get("realm_axis_name") or "境界主轴").strip()
    realm_ladder_line = " → ".join(level_names) if level_names else "（境界轴待定）"

    system = (
        "你是番茄修仙世界金手指设计师，深知修仙爽点来自数值爬升，"
        "金手指必须咬合境界体系并带代价。只返回 JSON，不要解释文字。"
    )
    prompt = build_xianxia_golden_finger_prompt(
        core_satisfaction=xp.get("core_satisfaction", ""),
        progression_fantasy=xp.get("progression_fantasy", ""),
        tension_source=xp.get("tension_source", ""),
        realm_axis_name=realm_axis_name,
        realm_ladder_line=realm_ladder_line,
    )
    data = await call_bootstrap_json_once(
        svc,
        step="golden_finger_xianxia",
        system=system,
        prompt=prompt,
        task="bootstrap.positioning",
        validate=_validate,
    )

    extra = dict(project.extra or {})
    extra["golden_finger"] = data
    project.extra = extra
    flag_modified(project, "extra")
    svc.db.commit()

    ctx["golden_finger"] = data
    return data
