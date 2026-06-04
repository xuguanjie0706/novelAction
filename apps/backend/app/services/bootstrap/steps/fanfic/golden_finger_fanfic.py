"""同人金手指：复用番茄步骤，注入同人上下文。"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.steps.fanfic._helpers import (
    entry_as_contrast,
    fanfic_as_fanqie_positioning,
    trope_info_edge,
)
from app.services.bootstrap.steps.fanqie.golden_finger import gen_golden_finger


async def gen_golden_finger_fanfic(svc: Any, project: Project, ctx: dict) -> dict:
    pos = fanfic_as_fanqie_positioning(ctx)
    # 按穿书/重生/AU 分流信息差来源（同人金手指核心爽点），并入 differentiation 供金手指 prompt 消费。
    edge = trope_info_edge(ctx)
    pos["differentiation"] = f"{pos.get('differentiation', '')}｜{edge}".strip("｜")
    ctx["fanqie_positioning"] = pos
    contrast = entry_as_contrast(ctx)
    contrast["trope_info_edge"] = edge
    ctx["contrast_design"] = contrast
    data = await gen_golden_finger(svc, project, ctx)
    if data:
        ctx["golden_finger"] = data
    return data
