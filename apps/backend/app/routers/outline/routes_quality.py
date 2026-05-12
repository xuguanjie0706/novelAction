"""大纲质检、修复工作流、快照修订列表。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OutlineRevision
from app.services.workflow_graph import workflow_runs

from app.routers.outline.helpers_core import _create_outline_revision
from app.routers.outline.qa_internal import (
    _execute_outline_quality_graph,
    _noop_outline_progress,
    _run_outline_quality_workflow,
    _run_outline_repair_workflow,
)
from app.routers.outline.schemas import (
    OutlineQualityCheckRequest,
    OutlineQualityWorkflowStartResponse,
    OutlineRepairRequest,
    OutlineSnapshotRequest,
)

router = APIRouter()

@router.post("/ai-quality-check")
async def ai_quality_check_outline(
    project_id: str,
    req: OutlineQualityCheckRequest,
    db: Session = Depends(get_db),
):
    """
    独立大纲质检接口：读取当前已入库的大纲章节计划，先逐卷质检并写回卷节点，
    再做全书级质检并写回项目 story_core。
    与全量生成拆开，避免生成失败和质检失败互相污染。
    """
    result_context = await _execute_outline_quality_graph({
        "db": db,
        "project_id": project_id,
        "req": req,
        "publish": _noop_outline_progress,
    })
    return result_context["result"]


@router.post("/ai-quality-check/workflow", response_model=OutlineQualityWorkflowStartResponse)
async def start_ai_quality_check_outline_workflow(
    project_id: str,
    req: OutlineQualityCheckRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start the graph-backed outline QA workflow.
    Progress is delivered through:
    /api/v1/projects/{project_id}/outline/workflows/{run_id}/ws
    """
    run_id = await workflow_runs.create_run(
        "outline_quality_check",
        {
            "project_id": project_id,
            "model_profile": req.model_profile,
        },
    )
    background_tasks.add_task(
        _run_outline_quality_workflow,
        run_id,
        project_id,
        req.model_dump(mode="json"),
    )
    return OutlineQualityWorkflowStartResponse(run_id=run_id)


@router.post("/ai-repair/workflow", response_model=OutlineQualityWorkflowStartResponse)
async def start_ai_repair_outline_workflow(
    project_id: str,
    req: OutlineRepairRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start the graph-backed outline repair workflow.
    It creates pre/post outline revisions and streams progress over the same
    workflow WebSocket endpoint.
    """
    run_id = await workflow_runs.create_run(
        "outline_repair",
        {
            "project_id": project_id,
            "model_profile": req.model_profile,
            "scope": req.scope,
        },
    )
    background_tasks.add_task(
        _run_outline_repair_workflow,
        run_id,
        project_id,
        req.model_dump(mode="json"),
    )
    return OutlineQualityWorkflowStartResponse(run_id=run_id)


@router.get("/revisions")
def list_outline_revisions(project_id: str, db: Session = Depends(get_db)):
    revisions = db.query(OutlineRevision).filter(
        OutlineRevision.project_id == project_id,
    ).order_by(OutlineRevision.created_at.desc()).limit(50).all()
    return [
        {
            "id": str(rev.id),
            "label": rev.label,
            "source": rev.source,
            "scope": rev.scope,
            "volume_node_id": str(rev.volume_node_id) if rev.volume_node_id else None,
            "note": rev.note,
            "node_count": rev.node_count,
            "meta": rev.meta or {},
            "created_at": rev.created_at.isoformat() if rev.created_at else None,
        }
        for rev in revisions
    ]


@router.get("/revisions/{revision_id}")
def get_outline_revision(project_id: str, revision_id: str, db: Session = Depends(get_db)):
    revision = db.query(OutlineRevision).filter(
        OutlineRevision.id == revision_id,
        OutlineRevision.project_id == project_id,
    ).first()
    if not revision:
        raise HTTPException(404, "Outline revision not found")
    return {
        "id": str(revision.id),
        "label": revision.label,
        "source": revision.source,
        "scope": revision.scope,
        "volume_node_id": str(revision.volume_node_id) if revision.volume_node_id else None,
        "note": revision.note,
        "node_count": revision.node_count,
        "meta": revision.meta or {},
        "snapshot": revision.snapshot,
        "created_at": revision.created_at.isoformat() if revision.created_at else None,
    }


@router.post("/revisions")
def create_outline_revision(project_id: str, req: OutlineSnapshotRequest, db: Session = Depends(get_db)):
    revision = _create_outline_revision(
        db,
        project_id=project_id,
        label=req.label,
        source="manual",
        scope=req.scope,
        volume_node_id=req.volume_node_id,
        note=req.note,
    )
    return {
        "id": str(revision.id),
        "label": revision.label,
        "source": revision.source,
        "scope": revision.scope,
        "volume_node_id": str(revision.volume_node_id) if revision.volume_node_id else None,
        "note": revision.note,
        "node_count": revision.node_count,
        "meta": revision.meta or {},
        "created_at": revision.created_at.isoformat() if revision.created_at else None,
    }

