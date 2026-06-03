"""番茄 Bootstrap 产物注入 ctx，供 gen_volumes 等通用步骤复用。"""
from __future__ import annotations

from typing import Any


def merge_fanqie_extra_into_ctx(project: Any, ctx: dict) -> dict:
    """将 Project.extra 中的番茄规划块并入 ctx（单步重跑卷纲时使用）。"""
    extra = project.extra if isinstance(getattr(project, "extra", None), dict) else {}
    for key in (
        "fanqie_positioning",
        "contrast_design",
        "golden_finger",
        "face_slap_map",
        "power_ladder",
        "rhythm_map",
        "opening_5chapters",
    ):
        if extra.get(key):
            ctx[key] = extra[key]
    return ctx
