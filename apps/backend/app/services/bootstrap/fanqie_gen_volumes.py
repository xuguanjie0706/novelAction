"""番茄存量项目：补跑全书卷纲（gen_volumes）。"""
from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from app.models import OutlineNode, Project
from app.services.bootstrap.step_regen import build_full_ctx, wipe_step
from app.services.bootstrap.steps.volumes import gen_volumes
from app.services.outline_planning import words_to_plan


def _needs_volume_regen(db: Session, project: Project) -> bool:
    """仅 1 卷且无导演单节拍时视为未生成卷纲。"""
    vols = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.node_type == "volume",
        )
        .all()
    )
    plan = words_to_plan(int(project.target_words or 1_200_000))
    if len(vols) < plan["total_volumes"]:
        return True
    if len(vols) == 1:
        ex = vols[0].extra or {}
        if not ex.get("beat_highlights") and not (vols[0].summary or "").strip():
            return True
    return False


async def regenerate_fanqie_volumes(db: Session, project: Project) -> list[OutlineNode]:
    """
    删除旧卷节点（含其下章纲）后重跑 gen_volumes。
    用于 Bootstrap 早于「卷纲步骤」的存量番茄项目。
    """
    wipe_step(db, str(project.id), "volumes")
    ctx = build_full_ctx(db, project)
    from app.services.bootstrap.fanqie_ctx import merge_fanqie_extra_into_ctx

    merge_fanqie_extra_into_ctx(project, ctx)

    from app.services.generation_service import GenerationService

    svc = GenerationService(db=db, model_profile="gemini")
    nodes = await gen_volumes(svc, project, ctx, inject_realm_fix_hint=False)
    return nodes or []


def regenerate_fanqie_volumes_sync(db: Session, project_id: str) -> int:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"project not found: {project_id}")
    if not _needs_volume_regen(db, project):
        vol_count = (
            db.query(OutlineNode)
            .filter(
                OutlineNode.project_id == project.id,
                OutlineNode.node_type == "volume",
            )
            .count()
        )
        return vol_count
    nodes = asyncio.run(regenerate_fanqie_volumes(db, project))
    return len(nodes)
