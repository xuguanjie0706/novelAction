"""章纲 linter：lint / repair-seed / 勾选修复。"""

from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OutlineNode, Project
from app.services.ai_service import AIService
from app.services.outline_linter import run_volume_linter_with_repair_seed
from app.services.outline_linter.linter_fix_service import (
    apply_linter_fix_patches,
    generate_linter_fix_patches,
    relint_volume_and_update_block_state,
)
from app.services.outline_linter.run import run_volume_linter_enriched

router = APIRouter()
logger = logging.getLogger(__name__)


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


class LinterFixRequest(BaseModel):
    """勾选 linter 问题定向修复。"""

    model_config = ConfigDict(protected_namespaces=())

    selected_indices: list[int]
    user_prompt: str = ""
    model_profile: Literal["local", "gemini", "default"] = "gemini"
    llm_provider_id: UUID | None = None


class LinterFixApplied(BaseModel):
    issue_index: int
    chapter_number: int | None = None
    rule_id: str = ""
    fields_changed: list[str] = []
    reason: str = ""
    applied: bool = True


class LinterFixSkipped(BaseModel):
    issue_index: int
    reason: str
    suggestion: str = ""


class LinterFixResponse(BaseModel):
    applied: list[LinterFixApplied]
    skipped: list[LinterFixSkipped]
    message: str
    linter_status: str
    linter_blocked: bool
    linter_report: dict[str, Any]


def _positioning_context(project: Project) -> str:
    extra = project.extra if isinstance(project.extra, dict) else {}
    pos = extra.get("positioning") or {}
    if not isinstance(pos, dict):
        return ""
    parts = [
        f"目标读者：{pos.get('target_audience', '')}",
        f"爽点：{pos.get('selling_point', '')}",
        f"节奏：{pos.get('pace_type', '')}",
    ]
    return "\n".join(p for p in parts if p.split("：", 1)[-1])


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
    return run_volume_linter_with_repair_seed(
        db, project, volume_node, report=report,
    )


@router.post("/volumes/{volume_node_id}/linter/fix", response_model=LinterFixResponse)
async def fix_linter_issues(
    project_id: str,
    volume_node_id: str,
    payload: LinterFixRequest,
    db: Session = Depends(get_db),
):
    """
    勾选 volume.extra.linter_issues 中的问题，AI 生成定向补丁并落库，随后自动 relint。
    """
    project, volume_node = _get_volume_or_404(db, project_id, volume_node_id)

    vol_extra = volume_node.extra if isinstance(volume_node.extra, dict) else {}
    issues_raw = vol_extra.get("linter_issues") or []
    if not isinstance(issues_raw, list) or not issues_raw:
        raise HTTPException(400, "该卷尚无 linter 问题记录，请先运行检测")

    indices = sorted({i for i in payload.selected_indices if isinstance(i, int)})
    if not indices:
        raise HTTPException(400, "请至少勾选一项 linter 问题")

    selected_pairs: list[tuple[int, dict]] = []
    for idx in indices:
        if idx < 0 or idx >= len(issues_raw):
            continue
        iss = issues_raw[idx]
        if isinstance(iss, dict):
            selected_pairs.append((idx, iss))
    if not selected_pairs:
        raise HTTPException(400, "所选序号无效")

    from app.routers.outline.helpers.revisions import _load_volume_chapter_context

    chapters = _load_volume_chapter_context(db, project_id, volume_node)
    chapters_by_number = {
        c["number"]: c for c in chapters if isinstance(c.get("number"), int)
    }

    profile = payload.model_profile if payload.model_profile != "default" else "gemini"
    svc = AIService(profile=profile, db=db, llm_provider_id=payload.llm_provider_id)
    plan = await generate_linter_fix_patches(
        svc,
        project_title=project.title,
        genre=project.genre or "玄幻",
        selected_pairs=selected_pairs,
        chapters_by_number=chapters_by_number,
        positioning_context=_positioning_context(project),
        user_prompt=payload.user_prompt,
    )

    if plan.get("error"):
        raise HTTPException(502, f"AI 修复失败：{plan['error']}")

    patches = plan.get("patches") if isinstance(plan.get("patches"), list) else []
    applied, skipped = apply_linter_fix_patches(
        db,
        project_id,
        volume_node,
        patches,
        selected_pairs=selected_pairs,
    )

    db.refresh(volume_node)
    relint = relint_volume_and_update_block_state(db, project, volume_node)

    msg_parts = [plan.get("summary") or f"已应用 {len(applied)} 条补丁"]
    if relint.get("linter_blocked"):
        msg_parts.append("仍有阻断级问题，请继续勾选修复或手动编辑")
    else:
        msg_parts.append("质量门控已通过，草稿可正式采用")

    return LinterFixResponse(
        applied=[LinterFixApplied(**a) for a in applied],
        skipped=[LinterFixSkipped(**s) for s in skipped],
        message="；".join(str(p) for p in msg_parts if p),
        linter_status=str(relint.get("linter_status", "unknown")),
        linter_blocked=bool(relint.get("linter_blocked")),
        linter_report=relint.get("linter_report") or {},
    )
