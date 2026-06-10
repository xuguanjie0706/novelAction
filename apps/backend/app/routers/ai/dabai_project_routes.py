"""dabai 主链路写作 / 一致性 API（Project + Chapter）。"""
from __future__ import annotations

import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Chapter, Project
from app.models.user import User
from app.routers.ai.dabai_draft_handlers import dabai_draft_assist_event_stream
from app.services.ai_service import AIService
from app.services.dabai.debrief_apply import apply_dabai_debrief
from app.services.dabai.quality_check import run_dabai_quality
from app.utils.dabai_mode import is_dabai_project

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_dabai_chapter(db: Session, project_id: str, chapter_id: UUID) -> tuple[Project, Chapter]:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or not is_dabai_project(project):
        raise HTTPException(404, "非 dabai 项目")
    chapter = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.project_id == project_id)
        .first()
    )
    if not chapter:
        raise HTTPException(404, "章节不存在")
    return project, chapter


class DabaiConsistencyRequest(BaseModel):
    chapter_id: UUID
    mode: Literal["rules", "full"] = "full"   # rules=纯规则秒回；full=规则+LLM 衔接/五拍/钩子
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None


@router.post("/dabai-consistency-check")
async def dabai_consistency_check(
    project_id: str,
    req: DabaiConsistencyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """dabai 质检 v2：规则一致性（阻断）+ LLM 衔接/五拍/钩子（提醒，可降级）。"""
    project, chapter = _get_dabai_chapter(db, project_id, req.chapter_id)
    svc = AIService(
        profile=req.model_profile, db=db,
        llm_provider_id=req.llm_provider_id, user_id=user.id,
    )
    report = await run_dabai_quality(
        svc, db, project, chapter, with_llm=(req.mode == "full"),
    )
    chapter.last_quality_report = report
    chapter.last_quality_score = report.get("overall_score")
    db.commit()
    return report


class DabaiDebriefRequest(BaseModel):
    chapter_id: UUID
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None


@router.post("/dabai-debrief")
async def dabai_debrief(
    project_id: str,
    req: DabaiDebriefRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """dabai 章末复盘：提取图事实/向量记忆 → Neo4j + MemoryChunk（幂等，可重跑）。"""
    project, chapter = _get_dabai_chapter(db, project_id, req.chapter_id)
    if not (chapter.content or "").strip():
        raise HTTPException(400, "本章还没有正文，无法复盘")
    svc = AIService(
        profile=req.model_profile, db=db,
        llm_provider_id=req.llm_provider_id, user_id=user.id,
    )
    try:
        result = await apply_dabai_debrief(db, project, chapter, svc)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("dabai 复盘失败 chapter=%s", req.chapter_id)
        raise HTTPException(500, f"复盘失败：{exc}") from exc
    return {"chapter_id": str(req.chapter_id), **result}


class DabaiDraftRequest(BaseModel):
    chapter_id: UUID
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None
    user_prompt: Optional[str] = None
    replace_existing: bool = False


@router.post("/dabai-draft-stream")
async def dabai_draft_stream(
    project_id: str,
    req: DabaiDraftRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """dabai 主链路流式写章（与 draft-assist dabai 分支同源 prompt）。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or not is_dabai_project(project):
        raise HTTPException(404, "非 dabai 项目")
    chapter = (
        db.query(Chapter)
        .filter(Chapter.id == req.chapter_id, Chapter.project_id == project_id)
        .first()
    )
    if not chapter:
        raise HTTPException(404, "章节不存在")

    if req.replace_existing:
        from app.routers.chapters import clear_chapter_rewrite_derivatives
        clear_chapter_rewrite_derivatives(db, project_id, str(req.chapter_id))
        db.commit()
        db.refresh(chapter)

    svc = AIService(
        profile=req.model_profile, db=db,
        llm_provider_id=req.llm_provider_id, user_id=user.id,
    )

    async def gen():
        async for line in dabai_draft_assist_event_stream(
            db,
            svc,
            project,
            chapter,
            str(project_id),
            user_prompt=(req.user_prompt or "").strip(),
            replace_existing=bool(req.replace_existing),
            stream_log_ctx={
                "project_id": str(project_id),
                "chapter_id": str(req.chapter_id),
            },
        ):
            yield line

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
