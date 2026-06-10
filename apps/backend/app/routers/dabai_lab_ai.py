"""dabai 实验书架写作期 AI 端点（质检 / 复盘 / 记忆 / 线索 / 预警查询）。

资源边界：仅操作 dabai_* 表，与精品文主链路隔离。路由前缀 /dabai，
挂在 /api/v1 下（main.py 统一鉴权）。CRUD 之外的生成端点均按
mock 项目支持离线降级（质检只跑规则、复盘走启发式）。
"""
from __future__ import annotations

import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import (
    DabaiAsset, DabaiClue, DabaiMemory, DabaiPreWarnRecord,
    DabaiQualityReport, DabaiRelation,
)
from app.models.user import User
from app.routers.dabai import _owned_or_404
from app.services.dabai.lab_debrief import run_lab_debrief
from app.services.dabai.lab_ledger import seed_ledgers
from app.services.dabai.lab_quality import run_lab_quality

logger = logging.getLogger("dabai.lab_ai")

router = APIRouter(prefix="/dabai", tags=["dabai-lab-ai"])


class LabAiRequest(BaseModel):
    """质检/复盘通用请求体：模型线路与 mock 开关，沿用写章约定。"""

    mock: bool = Field(default=False, description="离线 mock（不调真实 LLM）")
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None
    mode: Literal["rules", "full"] = "full"  # 仅质检用：rules=只跑规则层


def _chapter_or_404(
    db: Session, project: DabaiProject, chapter_id: UUID,
) -> DabaiChapterOutline:
    ch = (
        db.query(DabaiChapterOutline)
        .filter(DabaiChapterOutline.id == chapter_id,
                DabaiChapterOutline.project_id == project.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="章节不存在")
    return ch


def _build_ai(req: LabAiRequest, db: Session, user: User):
    from app.services.ai.service import AIService
    return AIService(profile=req.model_profile, db=db,
                     llm_provider_id=req.llm_provider_id, user_id=user.id)


# ── 质检 ─────────────────────────────────────────────────────────────────────
@router.post("/projects/{project_id}/chapters/{chapter_id}/quality-check")
async def lab_quality_check(
    project_id: UUID,
    chapter_id: UUID,
    req: LabAiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """跑一次章节质检（规则 + LLM），报告落库并返回。"""
    project = _owned_or_404(db, project_id, user)
    ch = _chapter_or_404(db, project, chapter_id)
    if not (ch.content or "").strip():
        raise HTTPException(status_code=400, detail="本章尚无正文，无法质检")
    with_llm = req.mode == "full" and not req.mock
    svc = _build_ai(req, db, user) if with_llm else None
    return await run_lab_quality(svc, db, project, ch, with_llm=with_llm)


@router.get("/projects/{project_id}/chapters/{chapter_id}/quality-report")
def lab_quality_report(
    project_id: UUID,
    chapter_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """最新一份落库质检报告；无则 {"report": null}。"""
    project = _owned_or_404(db, project_id, user)
    row = (
        db.query(DabaiQualityReport)
        .filter(DabaiQualityReport.project_id == project.id,
                DabaiQualityReport.chapter_id == chapter_id)
        .order_by(DabaiQualityReport.created_at.desc())
        .first()
    )
    return {"report": row.report if row else None,
            "created_at": row.created_at.isoformat() if row and row.created_at else None}


# ── 复盘（记忆 + 线索）──────────────────────────────────────────────────────
@router.post("/projects/{project_id}/chapters/{chapter_id}/debrief")
async def lab_debrief(
    project_id: UUID,
    chapter_id: UUID,
    req: LabAiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """章末复盘：提取记忆与线索并落库（幂等可重跑）。"""
    project = _owned_or_404(db, project_id, user)
    ch = _chapter_or_404(db, project, chapter_id)
    svc = None if req.mock else _build_ai(req, db, user)
    try:
        return await run_lab_debrief(svc, db, project, ch, mock=req.mock)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── 记忆库 ───────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/memory")
def lab_memory_list(
    project_id: UUID,
    chapter_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """记忆条目列表（可按章过滤），按章号倒序。"""
    project = _owned_or_404(db, project_id, user)
    q = db.query(DabaiMemory).filter(DabaiMemory.project_id == project.id)
    if chapter_id:
        q = q.filter(DabaiMemory.chapter_id == chapter_id)
    rows = q.order_by(DabaiMemory.chapter_number.desc(),
                      DabaiMemory.importance.desc()).limit(500).all()
    return {"items": [{
        "id": str(m.id), "chapter_id": str(m.chapter_id),
        "chapter_number": m.chapter_number, "mem_type": m.mem_type,
        "content": m.content, "importance": m.importance, "tags": m.tags or [],
    } for m in rows], "total": len(rows)}


# ── 线索台账 ─────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/clues")
def lab_clue_list(
    project_id: UUID,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """线索列表（可按 open/resolved/dropped 过滤），按埋设章号排序。"""
    project = _owned_or_404(db, project_id, user)
    q = db.query(DabaiClue).filter(DabaiClue.project_id == project.id)
    if status in ("open", "resolved", "dropped"):
        q = q.filter(DabaiClue.status == status)
    rows = q.order_by(DabaiClue.chapter_planted, DabaiClue.created_at).all()
    return {"items": [{
        "id": str(c.id), "title": c.title, "clue_type": c.clue_type,
        "description": c.description, "chapter_planted": c.chapter_planted,
        "chapter_resolved": c.chapter_resolved, "status": c.status,
        "source": c.source,
    } for c in rows], "total": len(rows)}


class CluePatch(BaseModel):
    status: Literal["open", "resolved", "dropped"]
    chapter_resolved: Optional[int] = None


@router.patch("/projects/{project_id}/clues/{clue_id}")
def lab_clue_patch(
    project_id: UUID,
    clue_id: UUID,
    req: CluePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """手动改线索状态（误判回收/弃用线索时纠偏）。"""
    project = _owned_or_404(db, project_id, user)
    clue = db.query(DabaiClue).filter(DabaiClue.id == clue_id,
                                      DabaiClue.project_id == project.id).first()
    if not clue:
        raise HTTPException(status_code=404, detail="线索不存在")
    clue.status = req.status
    if req.status == "resolved":
        clue.chapter_resolved = req.chapter_resolved or clue.chapter_resolved
    elif req.status == "open":
        clue.chapter_resolved = None
    db.commit()
    return {"ok": True, "id": str(clue.id), "status": clue.status}


# ── 资产台账 ─────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/assets")
def lab_asset_list(
    project_id: UUID,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """资产列表（功法/道具/金手指；可按状态与类型过滤）。首次访问惰性种子。"""
    project = _owned_or_404(db, project_id, user)
    seed_ledgers(db, project)
    q = db.query(DabaiAsset).filter(DabaiAsset.project_id == project.id)
    if status in ("active", "consumed", "lost"):
        q = q.filter(DabaiAsset.status == status)
    if kind in ("skill", "item", "golden_finger"):
        q = q.filter(DabaiAsset.kind == kind)
    rows = q.order_by(DabaiAsset.kind, DabaiAsset.acquired_chapter,
                      DabaiAsset.created_at).all()
    return {"items": [{
        "id": str(a.id), "kind": a.kind, "name": a.name, "owner": a.owner,
        "description": a.description, "acquired_chapter": a.acquired_chapter,
        "status": a.status, "status_chapter": a.status_chapter, "source": a.source,
    } for a in rows], "total": len(rows)}


class AssetPatch(BaseModel):
    status: Literal["active", "consumed", "lost"]


@router.patch("/projects/{project_id}/assets/{asset_id}")
def lab_asset_patch(
    project_id: UUID,
    asset_id: UUID,
    req: AssetPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """手动改资产状态（复盘误判时纠偏）。"""
    project = _owned_or_404(db, project_id, user)
    row = db.query(DabaiAsset).filter(DabaiAsset.id == asset_id,
                                      DabaiAsset.project_id == project.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="资产不存在")
    row.status = req.status
    db.commit()
    return {"ok": True, "id": str(row.id), "status": row.status}


# ── 关系台账 ─────────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/relations")
def lab_relation_list(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """人物关系列表（主角视角态度 + 完整变化轨迹）。首次访问惰性种子。"""
    project = _owned_or_404(db, project_id, user)
    seed_ledgers(db, project)
    rows = (
        db.query(DabaiRelation)
        .filter(DabaiRelation.project_id == project.id)
        .order_by(DabaiRelation.last_change_chapter.desc().nullslast(),
                  DabaiRelation.created_at)
        .all()
    )
    return {"items": [{
        "id": str(r.id), "from_name": r.from_name, "to_name": r.to_name,
        "attitude": r.attitude, "note": r.note,
        "last_change_chapter": r.last_change_chapter,
        "history": r.history or [], "source": r.source,
    } for r in rows], "total": len(rows)}


class RelationPatch(BaseModel):
    attitude: str
    reason: Optional[str] = None


@router.patch("/projects/{project_id}/relations/{relation_id}")
def lab_relation_patch(
    project_id: UUID,
    relation_id: UUID,
    req: RelationPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """手动改人物态度（追加 history，chapter 为空表示手动）。"""
    project = _owned_or_404(db, project_id, user)
    row = db.query(DabaiRelation).filter(DabaiRelation.id == relation_id,
                                         DabaiRelation.project_id == project.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="关系不存在")
    attitude = req.attitude.strip()[:40]
    if not attitude:
        raise HTTPException(status_code=400, detail="attitude 不能为空")
    history = list(row.history or [])
    history.append({"chapter": None, "attitude": attitude,
                    "reason": (req.reason or "手动修改")[:120]})
    row.attitude, row.history = attitude, history
    db.commit()
    return {"ok": True, "id": str(row.id), "attitude": row.attitude}


# ── 预警（写前导演单）查询 ───────────────────────────────────────────────────
@router.get("/projects/{project_id}/chapters/{chapter_id}/pre-warn")
def lab_pre_warn_latest(
    project_id: UUID,
    chapter_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """本章最新一条落库导演单；无则 {"record": null}。"""
    project = _owned_or_404(db, project_id, user)
    row = (
        db.query(DabaiPreWarnRecord)
        .filter(DabaiPreWarnRecord.project_id == project.id,
                DabaiPreWarnRecord.chapter_id == chapter_id)
        .order_by(DabaiPreWarnRecord.created_at.desc())
        .first()
    )
    return {"record": ({
        "version": row.version, "result": row.result or {},
        "brief": row.brief or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    } if row else None)}
