"""质检根因台账 —— 路由层。

资源边界：仅暴露根因台账的查询、聚合（高频根因发现）与手动深度分析；
自动落库+归因由 ``quality_routes.quality_check`` 在质检后 best-effort 触发，不在此处。
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, Character, Project, QualityRootCauseLog, StoryLine
from app.schemas.quality_root_cause import (
    QualityRootCauseOut,
    RootCauseAggregateRow,
    RootCauseAnalyzeRequest,
)
from app.services.ai_service import AIService
from app.services.ai.prompts.quality_root_cause_prompt import CATEGORIES
from app.services.ai.quality_root_cause import (
    analyze_root_causes,
    build_system_knowledge_brief,
    load_draft_context_note,
)
from app.services.bootstrap.power_registry import build_draft_power_context_from_db

router = APIRouter()


@router.get("/quality-root-cause/logs", response_model=list[QualityRootCauseOut])
def list_root_cause_logs(
    project_id: str,
    chapter_id: Optional[str] = None,
    status: Optional[str] = Query(None, description="pending/analyzed/failed/dismissed"),
    category: Optional[str] = Query(None, description="按根因分类过滤"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """质检根因台账列表（新→旧）。"""
    q = db.query(QualityRootCauseLog).filter(QualityRootCauseLog.project_id == project_id)
    if chapter_id:
        q = q.filter(QualityRootCauseLog.chapter_id == chapter_id)
    if status:
        q = q.filter(QualityRootCauseLog.analysis_status == status)
    if category:
        q = q.filter(QualityRootCauseLog.root_cause_category == category)
    return (
        q.order_by(QualityRootCauseLog.updated_at.desc(), QualityRootCauseLog.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/quality-root-cause/aggregate", response_model=list[RootCauseAggregateRow])
def aggregate_root_causes(
    project_id: str,
    group_by: str = Query("category", description="category（根因分类）/ dimension（质检维度）"),
    db: Session = Depends(get_db),
):
    """高频根因发现视图：按根因分类或质检维度聚合命中次数，降序。

    这是「让模型/作者发现为什么反复犯错」的核心入口——次数最高的根因即最该优先修的管线缺陷。
    """
    col = (
        QualityRootCauseLog.dimension
        if group_by == "dimension"
        else QualityRootCauseLog.root_cause_category
    )
    rows = (
        db.query(
            col.label("key"),
            func.coalesce(func.sum(QualityRootCauseLog.occurrence_count), 0).label("occ"),
            func.count(QualityRootCauseLog.id).label("cnt"),
        )
        .filter(QualityRootCauseLog.project_id == project_id)
        .group_by(col)
        .order_by(func.coalesce(func.sum(QualityRootCauseLog.occurrence_count), 0).desc())
        .all()
    )
    out: list[RootCauseAggregateRow] = []
    for r in rows:
        key = r.key or "未知"
        label = CATEGORIES.get(key, key) if group_by == "category" else key
        out.append(
            RootCauseAggregateRow(
                key=key,
                label=label,
                total_occurrences=int(r.occ or 0),
                distinct_items=int(r.cnt or 0),
            )
        )
    return out


@router.post("/quality-root-cause/analyze")
async def analyze_root_cause(
    project_id: str,
    req: RootCauseAnalyzeRequest,
    db: Session = Depends(get_db),
):
    """手动对某章 pending/failed 的根因条目重跑 LLM 归因（省 token 的按需深度分析）。"""
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    rows = (
        db.query(QualityRootCauseLog)
        .filter(
            QualityRootCauseLog.project_id == project_id,
            QualityRootCauseLog.chapter_id == req.chapter_id,
            QualityRootCauseLog.analysis_status.in_(["pending", "failed"]),
        )
        .all()
    )
    if not rows:
        return {"analyzed": 0, "message": "没有待分析的根因条目"}

    # 失败行复位为 pending，让 analyze 重新处理
    for r in rows:
        r.analysis_status = "pending"
    db.flush()

    characters = db.query(Character).filter(Character.project_id == project_id).all()
    character_states = [
        f"{c.name}：境界={c.current_realm or '未知'}，位置={c.current_location or '未知'}，"
        f"状态={c.current_status or 'alive'}"
        for c in characters
    ]
    storylines = (
        db.query(StoryLine)
        .filter(StoryLine.project_id == project_id, StoryLine.status.in_(["active", "climax"]))
        .all()
    )
    storylines_context = [f"{s.name}（{s.line_type}，{s.status}）" for s in storylines]
    power_summary = [build_draft_power_context_from_db(db, project_id)]
    brief = build_system_knowledge_brief(
        character_states=character_states,
        power_systems_summary=power_summary,
        storylines_context=storylines_context,
    )

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    note = load_draft_context_note(db, project_id, chapter)
    analyzed = await analyze_root_causes(svc, db, chapter, rows, brief, note)
    db.commit()
    return {"analyzed": analyzed, "total": len(rows)}
