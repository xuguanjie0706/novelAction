"""斗破线 Step 0：立项（斗气大陆纯爽文第一性原理，replaces 通用 positioning）。

产物：
- ``ctx['doupo_positioning']``：斗破原生定位（子类型/核心爽感/升级曲线/开局金手指/雷点）。
- ``ctx['positioning']``：映射为通用 positioning，供中立复用步骤（gen_project / storylines /
  memory / mysteries）读取，不让它们感知斗破细节。

字段集与修仙线一致（subgenre / core_satisfaction / ...），故 router 立项闸门校验复用
``try_validate_xianxia_positioning``，无需新增 schema。
红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

from typing import Any

from app.services.bootstrap.json_once import call_bootstrap_json_once
from app.services.bootstrap.prompts.doupo_prompts import (
    build_doupo_positioning_prompt,
    doupo_to_generic_positioning,
)

_REQUIRED = {
    "subgenre",
    "core_satisfaction",
    "progression_fantasy",
    "tension_source",
    "opening_fortune",
}

# 供 graph_doupo 复用（与 router 立项校验同名映射）
to_generic_positioning = doupo_to_generic_positioning


def _validate(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "根类型须为 JSON 对象"
    if missing := _REQUIRED - data.keys():
        return f"缺少字段：{missing}"
    if not (data.get("core_satisfaction") or "").strip():
        return "core_satisfaction 不能为空"
    if not (data.get("subgenre") or "").strip():
        return "subgenre 不能为空"
    return None


async def gen_doupo_positioning(svc: Any, ctx: dict) -> dict:
    """召开斗破式立项会议；产物写入 ctx['doupo_positioning'] + ctx['positioning']。

    @returns doupo_positioning dict
    @raises BootstrapStepError: JSON 解析或字段校验失败
    """
    system = (
        "你是深耕番茄男频斗气大陆纯爽文（斗破苍穹式）的资深主编，深知爽感来自斗气阶位爬升、"
        "越阶斗技碾压、炼药夺宝与扮猪吃虎打脸，而非修仙渡劫成仙。只返回 JSON，不要任何解释文字。"
    )
    prompt = build_doupo_positioning_prompt(
        logline=ctx.get("logline", ""),
        premise=ctx.get("premise", ""),
    )
    data = await call_bootstrap_json_once(
        svc,
        step="doupo_positioning",
        system=system,
        prompt=prompt,
        task="bootstrap.positioning",
        validate=_validate,
    )
    ctx["doupo_positioning"] = data
    ctx["positioning"] = doupo_to_generic_positioning(data)
    return data
