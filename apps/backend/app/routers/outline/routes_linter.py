"""章纲 linter：POST /outline/volumes/{volume_node_id}/lint"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OutlineNode, Project
from app.services.outline_linter import (
    apply_volume_linter,
    run_volume_linter_with_repair_seed,
)
from app.services.outline_linter.run import run_volume_linter_enriched

router = APIRouter()


def _get_volume_or_404(db: Session, project_id: str, volume_node_id: str):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    volume_node = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.id == volume_node_id,
            OutlineNode.project_id == project_id,
        )
        .first()
    )
    if not volume_node:
        raise HTTPException(404, "Volume node not found")
    if volume_node.node_type != "volume":
        raise HTTPException(422, f"节点类型必须为 volume，当前为 {volume_node.node_type!r}")
    count = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.parent_id == volume_node_id,
            OutlineNode.node_type == "chapter_plan",
        )
        .count()
    )
    if count == 0:
        raise HTTPException(400, "该卷尚无章节计划，无法 lint")
    return project, volume_node


@router.post("/volumes/{volume_node_id}/lint")
async def lint_volume_chapters(
    project_id: str,
    volume_node_id: str,
    persist: bool = Query(True),
    use_embedding: bool = Query(True),
    db: Session = Depends(get_db),
):
    """对指定卷的 chapter_plan 运行确定性 linter（含 SEQ-05/05E）。"""
    project, volume_node = _get_volume_or_404(db, project_id, volume_node_id)

    report = await run_volume_linter_enriched(
        db, project, volume_node, use_embedding=use_embedding,
    )
    if persist:
        from app.services.outline_linter.run import persist_linter_report
        from app.services.outline_linter.gate import _log_linter_report

        persist_linter_report(volume_node, report)
        db.commit()
        _log_linter_report(project, volume_node, report)
    return report.to_dict()


@router.post("/volumes/{volume_node_id}/lint/repair-seed")
async def lint_volume_repair_seed(
    project_id: str,
    volume_node_id: str,
    persist: bool = Query(True),
    use_embedding: bool = Query(True),
    db: Session = Depends(get_db),
):
    """运行 linter 并返回 repair_seed（供大纲修复工作流引用）。"""
    project, volume_node = _get_volume_or_404(db, project_id, volume_node_id)

    report = await run_volume_linter_enriched(
        db, project, volume_node, use_embedding=use_embedding,
    )
    if persist:
        from app.services.outline_linter.run import persist_linter_report

        persist_linter_report(volume_node, report)
        db.commit()
    from app.services.outline_linter.run import run_volume_linter_with_repair_seed

    return run_volume_linter_with_repair_seed(
        db, project, volume_node, report=report,
    )
