"""修仙直白线 Step 0：立项（修仙第一性原理，replaces algo_positioning）。

产物：
- ``ctx['xianxia_positioning']``：修仙原生定位（子类型/核心爽感/张力/开局机缘/升级节奏）。
- ``ctx['positioning']``：映射为通用 positioning，供中立复用步骤（gen_project / storylines /
  memory / mysteries）读取，不让它们感知修仙细节。

设计主张：番茄 algo_positioning 的核心爽感锁「打脸」，与修仙「数值爬升」引擎错配。
本步骤把整条线的语义锚点从打脸重定向到升级流——下游所有修仙原生步骤据此推导。
红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

from typing import Any

from app.services.bootstrap.json_once import call_bootstrap_json_once
from app.services.bootstrap.prompts.xianxia_positioning_prompt import (
    build_xianxia_positioning_prompt,
)

_STEP = "positioning"

_REQUIRED = {
    "subgenre",
    "core_satisfaction",
    "progression_fantasy",
    "tension_source",
    "opening_fortune",
}


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


def to_generic_positioning(xp: dict) -> dict:
    """修仙定位 → 通用 positioning（供中立复用步骤读取）。

    pace_type 固定 fast（修仙直白文快节奏），writing_style 固定 plain；
    face_slap_pattern 改用『升级碾压节奏』语义，避免给修仙线注入打脸框架。
    """
    return {
        "target_audience": f"番茄男频·修仙{xp.get('subgenre', '')}读者",
        "tropes": xp.get("reader_tags", []),
        "reference_works": [],
        "selling_point": xp.get("core_satisfaction", ""),
        # 修仙语义：用升级节奏替代打脸节奏（字段名沿用以兼容下游通用读取）
        "face_slap_pattern": xp.get("power_fantasy_curve", "")
        or "每3章一次小突破/碾压，每10章一次大境突破",
        "emotional_arc": f"修仙升级曲线：{xp.get('progression_fantasy', '蝼蚁→证道')}",
        "pace_type": "fast",
        "writing_style": "plain",
        "taboo_lines": (
            [str(xp["taboo_check"])] if xp.get("taboo_check") else ["无"]
        ),
    }


async def gen_xianxia_positioning(svc: Any, ctx: dict) -> dict:
    """召开修仙立项会议；产物写入 ctx['xianxia_positioning'] + ctx['positioning']。

    @returns xianxia_positioning dict
    @raises BootstrapStepError: JSON 解析或字段校验失败
    """
    system = (
        "你是深耕番茄玄幻修仙直白文的资深主编，深知修仙读者的爽感来自数值爬升、"
        "境界碾压、夺宝机缘，而非社交打脸。只返回 JSON，不要任何解释文字。"
    )
    prompt = build_xianxia_positioning_prompt(
        logline=ctx.get("logline", ""),
        premise=ctx.get("premise", ""),
    )
    data = await call_bootstrap_json_once(
        svc,
        step="xianxia_positioning",
        system=system,
        prompt=prompt,
        task="bootstrap.positioning",
        validate=_validate,
    )
    ctx["xianxia_positioning"] = data
    ctx["positioning"] = to_generic_positioning(data)
    return data
