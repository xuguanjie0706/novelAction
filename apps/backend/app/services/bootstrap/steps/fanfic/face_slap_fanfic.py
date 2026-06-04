"""同人打脸地图：复用番茄步骤。"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.steps.fanfic._helpers import fanfic_as_fanqie_positioning
from app.services.bootstrap.steps.fanqie.face_slap_map import gen_face_slap_map


async def gen_face_slap_fanfic(svc: Any, project: Project, ctx: dict) -> dict:
    ctx["fanqie_positioning"] = fanfic_as_fanqie_positioning(ctx)
    data = await gen_face_slap_map(svc, project, ctx)
    if data:
        ctx["face_slap_map"] = data
    return data
