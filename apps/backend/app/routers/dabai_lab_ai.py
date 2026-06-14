"""dabai 实验书架写作期 AI 端点（质检 / 复盘 / 记忆 / 线索 / 预警查询）。

资源边界：仅操作 dabai_* 表，与精品文主链路隔离。路由前缀 /dabai，
挂在 /api/v1 下（main.py 统一鉴权）。
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
    DabaiAsset, DabaiClue, DabaiMemory, DabaiPanelSnapshot,
    DabaiPreWarnRecord, DabaiQualityReport, DabaiRelation,
)
from app.models.user import User
from app.routers.dabai import _owned_or_404
from app.services.dabai.lab_debrief import run_lab_debrief
from app.services.dabai.lab_ledger import seed_ledgers
from app.services.dabai.lab_quality import run_lab_quality

logger = logging.getLogger("dabai.lab_ai")

router = APIRouter(prefix="/dabai", tags=["dabai-lab-ai"])


class LabAiRequest(BaseModel):
    """质检/复盘通用请求体：模型线路，沿用写章约定。"""

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
    with_llm = req.mode == "full"
    svc = _build_ai(req, db, user) if with_llm else None
    source = "manual" if req.mode == "full" else "rules"
    return await run_lab_quality(
        svc, db, project, ch, with_llm=with_llm, source=source,
    )


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
    return {
        "report": row.report if row else None,
        "report_id": str(row.id) if row else None,
        "created_at": row.created_at.isoformat() if row and row.created_at else None,
    }


@router.get("/projects/{project_id}/chapters/{chapter_id}/quality-reports")
def lab_quality_report_history(
    project_id: UUID,
    chapter_id: UUID,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """本章质检历史（最新在前，含快照字段）。"""
    from app.services.dabai.lab_quality_query import list_dabai_quality_reports

    project = _owned_or_404(db, project_id, user)
    _chapter_or_404(db, project, chapter_id)
    items = list_dabai_quality_reports(
        db,
        project_id=project.id,
        chapter_id=chapter_id,
        limit=min(max(limit, 1), 100),
        include_report=False,
    )
    return {"items": items, "total": len(items)}


@router.get("/projects/{project_id}/quality-debts")
def lab_quality_debts(
    project_id: UUID,
    threshold: int = 70,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """质量欠债清单：各章最新报告低于阈值或被阻断的章节（派生视图，无新表）。"""
    from app.services.dabai.lab_quality_query import list_dabai_quality_debts

    project = _owned_or_404(db, project_id, user)
    items = list_dabai_quality_debts(
        db, project.id, threshold=min(max(threshold, 0), 100),
    )
    return {"items": items, "total": len(items), "threshold": threshold}


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
    svc = _build_ai(req, db, user)
    try:
        return await run_lab_debrief(svc, db, project, ch)
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


def _serialize_memory(m: DabaiMemory, *, score: float | None = None) -> dict:
    """记忆条目序列化（与 lab_memory_list 字段对齐，可附语义相似度）。"""
    item = {
        "id": str(m.id), "chapter_id": str(m.chapter_id),
        "chapter_number": m.chapter_number, "mem_type": m.mem_type,
        "content": m.content, "importance": m.importance, "tags": m.tags or [],
    }
    if score is not None:
        item["score"] = round(score, 4)
    return item


@router.get("/projects/{project_id}/memory/search")
async def lab_memory_search(
    project_id: UUID,
    q: str,
    mode: Literal["semantic", "exact"] = "semantic",
    top_k: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """记忆库检索：semantic=pgvector 余弦召回（按相似度排序）；exact=子串匹配。

    语义模式在 pgvector 不可用 / 无向量化数据时自动降级为 exact，并以
    ``degraded=true`` + ``effective_mode`` 告知前端，便于提示用户补跑向量化。
    """
    project = _owned_or_404(db, project_id, user)
    query = (q or "").strip()
    if not query:
        return {"items": [], "total": 0, "mode": mode, "effective_mode": mode,
                "degraded": False}

    top_k = max(1, min(top_k, 50))

    if mode == "semantic":
        from app.services.dabai.lab_embedding import semantic_search_dabai

        hits = await semantic_search_dabai(db, project.id, query, top_k=top_k)
        if hits:
            return {
                "items": [_serialize_memory(m) for m in hits],
                "total": len(hits), "mode": "semantic",
                "effective_mode": "semantic", "degraded": False,
            }
        # 语义召回空（pgvector 不可用 / 存量未向量化）→ 降级子串匹配
        rows = _exact_memory_match(db, project.id, query, top_k)
        return {
            "items": [_serialize_memory(m) for m in rows],
            "total": len(rows), "mode": "semantic",
            "effective_mode": "exact", "degraded": True,
        }

    rows = _exact_memory_match(db, project.id, query, top_k)
    return {"items": [_serialize_memory(m) for m in rows], "total": len(rows),
            "mode": "exact", "effective_mode": "exact", "degraded": False}


def _exact_memory_match(
    db: Session, project_id: UUID, query: str, top_k: int,
) -> list[DabaiMemory]:
    """子串匹配（content 包含 query），按章号倒序 + 重要度。"""
    return (
        db.query(DabaiMemory)
        .filter(
            DabaiMemory.project_id == project_id,
            DabaiMemory.content.ilike(f"%{query}%"),
        )
        .order_by(DabaiMemory.chapter_number.desc(), DabaiMemory.importance.desc())
        .limit(top_k)
        .all()
    )


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
        # v2 数值字段
        "grade": a.grade,
        "base_stat": a.base_stat,
        "cooldown_chapters": a.cooldown_chapters,
        "last_used_chapter": a.last_used_chapter,
        "enhancement_level": a.enhancement_level or 0,
        # v3：导演单锁定的详细规格（用法/代价/进阶/限制）
        "spec": a.spec,
    } for a in rows], "total": len(rows)}


class AssetPatch(BaseModel):
    """手动纠偏资产：状态变更 + 可选的数值字段修正。"""

    status: Optional[Literal["active", "consumed", "lost"]] = None
    grade: Optional[int] = Field(default=None, ge=0, le=4)
    cooldown_chapters: Optional[int] = Field(default=None, ge=0)
    last_used_chapter: Optional[int] = Field(default=None, ge=0)
    base_stat: Optional[dict] = None
    enhancement_level: Optional[int] = Field(default=None, ge=0)
    spec: Optional[dict] = None   # 手动编辑详细规格（用法/代价/进阶/限制）


@router.patch("/projects/{project_id}/assets/{asset_id}")
def lab_asset_patch(
    project_id: UUID,
    asset_id: UUID,
    req: AssetPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """手动改资产状态或数值字段（复盘误判时纠偏）。"""
    project = _owned_or_404(db, project_id, user)
    row = db.query(DabaiAsset).filter(DabaiAsset.id == asset_id,
                                      DabaiAsset.project_id == project.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="资产不存在")
    if req.status is not None:
        row.status = req.status
    if req.grade is not None:
        row.grade = req.grade
    if req.cooldown_chapters is not None:
        row.cooldown_chapters = req.cooldown_chapters
    if req.last_used_chapter is not None:
        row.last_used_chapter = req.last_used_chapter
    if req.base_stat is not None:
        row.base_stat = req.base_stat
    if req.enhancement_level is not None:
        row.enhancement_level = req.enhancement_level
    if req.spec is not None:
        from app.services.dabai.lab_asset_spec import coerce_spec
        row.spec = coerce_spec(req.spec)
    db.commit()
    return {"ok": True, "id": str(row.id), "status": row.status, "grade": row.grade}


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


# ── 预警（写前导演单）────────────────────────────────────────────────────────
@router.post("/projects/{project_id}/chapters/{chapter_id}/pre-warn")
async def lab_pre_warn_run(
    project_id: UUID,
    chapter_id: UUID,
    req: LabAiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """手动生成/重跑写前导演单（落库并返回）。"""
    from app.services.dabai.lab_draft_context import build_lab_draft_context_async
    from app.services.dabai.lab_ledger import build_ledger_block
    from app.services.dabai.lab_pre_warn import PREWARN_VERSION, resolve_lab_pre_warn

    project = _owned_or_404(db, project_id, user)
    ch = _chapter_or_404(db, project, chapter_id)
    draft_ctx = await build_lab_draft_context_async(db, project, ch)
    seed_ledgers(db, project)
    ledger_block = build_ledger_block(db, project, ch)
    replace_existing = bool((ch.content or "").strip())
    svc = _build_ai(req, db, user)
    brief, evt, result = await resolve_lab_pre_warn(
        svc, project, ch, draft_ctx, db=db, ledger_block=ledger_block,
        replace_existing=replace_existing,
    )
    return {
        "record": ({
            "version": PREWARN_VERSION,
            "result": result or {},
            "brief": brief,
        } if result else None),
        "ok": evt.get("ok", False),
        "brief_injected": evt.get("brief_injected", False),
        "error": evt.get("error"),
    }


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


# ── 分场调度单 ───────────────────────────────────────────────────────────────
@router.post("/projects/{project_id}/chapters/{chapter_id}/scene-plan")
async def lab_scene_plan_run(
    project_id: UUID,
    chapter_id: UUID,
    req: LabAiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """手动生成/重跑分场调度单（落库并返回；依赖本章已有导演单）。"""
    from app.services.dabai.lab_draft_context import build_lab_draft_context_async
    from app.services.dabai.lab_ledger import build_ledger_block
    from app.services.dabai.lab_pre_warn import load_lab_pre_warn
    from app.services.dabai.lab_scene_plan import resolve_lab_scene_plan

    project = _owned_or_404(db, project_id, user)
    ch = _chapter_or_404(db, project, chapter_id)
    pre_warn_block, pre_warn_result = load_lab_pre_warn(db, ch.id)
    if not pre_warn_result:
        raise HTTPException(status_code=400, detail="请先在「预警」Tab 生成导演单")
    draft_ctx = await build_lab_draft_context_async(db, project, ch)
    seed_ledgers(db, project)
    ledger_block = build_ledger_block(db, project, ch)
    replace_existing = bool((ch.content or "").strip())
    svc = _build_ai(req, db, user)
    brief, evt, _result = await resolve_lab_scene_plan(
        svc, project, ch, draft_ctx, db=db,
        pre_warn_block=pre_warn_block, ledger_block=ledger_block,
        pre_warn_result=pre_warn_result,
        replace_existing=replace_existing,
    )
    record = None
    if evt.get("scene_count", 0) > 0:
        from app.models.dabai_lab import DabaiScenePlan
        row = (
            db.query(DabaiScenePlan)
            .filter(DabaiScenePlan.chapter_id == ch.id)
            .order_by(DabaiScenePlan.created_at.desc())
            .first()
        )
        if row:
            record = {
                "version": row.version,
                "scenes": row.scenes or [],
                "opening_line": row.opening_line or "",
                "brief": row.brief or brief,
            }
    return {
        "record": record,
        "ok": evt.get("ok", False),
        "scene_count": evt.get("scene_count", 0),
        "scene_names": evt.get("scene_names") or [],
        "error": evt.get("error"),
    }


@router.get("/projects/{project_id}/chapters/{chapter_id}/scene-plan")
def lab_scene_plan_latest(
    project_id: UUID,
    chapter_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """本章最新一条落库分场调度单；无则 {"record": null}。"""
    from app.models.dabai_lab import DabaiScenePlan

    project = _owned_or_404(db, project_id, user)
    row = (
        db.query(DabaiScenePlan)
        .filter(DabaiScenePlan.project_id == project.id,
                DabaiScenePlan.chapter_id == chapter_id)
        .order_by(DabaiScenePlan.created_at.desc())
        .first()
    )
    return {"record": ({
        "version": row.version, "scenes": row.scenes or [],
        "opening_line": row.opening_line or "", "brief": row.brief or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    } if row else None)}


# ── 系统面板快照 ─────────────────────────────────────────────────────────────
@router.get("/projects/{project_id}/panel-snapshot")
def lab_panel_snapshot_latest(
    project_id: UUID,
    chapter_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """最新一条系统面板快照（或指定章节的快照）。

    查询参数：
      chapter_id: 若传入则取该章快照；否则取全书最新（章号最大）的快照。

    返回：{"snapshot": {...} | null, "chapter_number": int | null}
    """
    project = _owned_or_404(db, project_id, user)
    q = db.query(DabaiPanelSnapshot).filter(
        DabaiPanelSnapshot.project_id == project.id,
    )
    if chapter_id:
        q = q.filter(DabaiPanelSnapshot.chapter_id == chapter_id)
    row = q.order_by(DabaiPanelSnapshot.chapter_number.desc()).first()
    if not row:
        return {"snapshot": None, "chapter_number": None}
    return {
        "snapshot": row.snapshot or {},
        "chapter_number": row.chapter_number,
        "chapter_id": str(row.chapter_id),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/projects/{project_id}/panel-snapshots")
def lab_panel_snapshot_list(
    project_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """全书面板快照列表（按章号倒序）；用于前端「系统面板时间线」。"""
    project = _owned_or_404(db, project_id, user)
    rows = (
        db.query(DabaiPanelSnapshot)
        .filter(DabaiPanelSnapshot.project_id == project.id)
        .order_by(DabaiPanelSnapshot.chapter_number.desc())
        .limit(200)
        .all()
    )
    return {"items": [{
        "id": str(r.id),
        "chapter_id": str(r.chapter_id),
        "chapter_number": r.chapter_number,
        "realm": (r.snapshot or {}).get("realm"),
        "sub_level": (r.snapshot or {}).get("sub_level"),
        "combat_power": (r.snapshot or {}).get("combat_power"),
        "snapshot": r.snapshot or {},
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows], "total": len(rows)}
