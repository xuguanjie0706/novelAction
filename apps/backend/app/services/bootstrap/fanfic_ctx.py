"""同人 Bootstrap 产物注入 ctx，供 gen_volumes 等通用步骤复用。"""
from __future__ import annotations

from typing import Any


def merge_fanfic_extra_into_ctx(project: Any, ctx: dict) -> dict:
    extra = project.extra if isinstance(getattr(project, "extra", None), dict) else {}
    for key in (
        "fanfic_meta",
        "fanfic_positioning",
        "fanfic_canon",
        "fanfic_deviation",
        "fanfic_entry",
        "fanfic_audit",
        "golden_finger",
        "face_slap_map",
        "power_ladder",
        "rhythm_map",
        "contrast_design",
    ):
        if extra.get(key):
            ctx[key] = extra[key]
    if extra.get("fanfic_positioning") and not ctx.get("fanqie_positioning"):
        from app.services.bootstrap.steps.fanfic._helpers import fanfic_as_fanqie_positioning

        ctx["fanqie_positioning"] = fanfic_as_fanqie_positioning(ctx)
    if extra.get("fanfic_entry") and not ctx.get("contrast_design"):
        from app.services.bootstrap.steps.fanfic._helpers import entry_as_contrast

        ctx["contrast_design"] = entry_as_contrast(ctx)
    return ctx
