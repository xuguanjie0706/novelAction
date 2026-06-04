"""同人爽点节奏：复用番茄步骤。"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.steps.fanfic._helpers import fanfic_as_fanqie_positioning
from app.services.bootstrap.steps.fanqie.rhythm_map import gen_rhythm_map


async def gen_rhythm_fanfic(svc: Any, project: Project, ctx: dict) -> dict:
    ctx["fanqie_positioning"] = fanfic_as_fanqie_positioning(ctx)
    data = await gen_rhythm_map(svc, project, ctx)
    if data:
        ctx["rhythm_map"] = data
    return data
