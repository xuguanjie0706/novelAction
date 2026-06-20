"""dabai 章节正文写作路由（PATCH 保存 + SSE 流式生成/重写）。"""
from __future__ import annotations

import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.dabai import DabaiChapterOutline
from app.models.user import User
from app.routers.dabai import _owned_or_404, _sse
from app.services.dabai.lab_chapter_gate import dabai_chapter_generate_block_reason
from app.services.dabai.lab_pre_warn import LabPreWarnError
from app.services.dabai.lab_scene_plan import LabScenePlanError
from app.services.dabai.prose.orchestrator import ProseWriteRequest, run_prose_pipeline

logger = logging.getLogger("dabai.api.draft")


class WriteRequest(BaseModel):
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None
    user_instruction: str = Field(default="", max_length=4000, description="作者写作指令，可为空")
    rewrite_mode: Literal["full", "qc_patch"] = "full"
    rerun_pre_warn: bool = False
    rerun_scene_plan: bool = False
    rerun_quality: bool = True
    rerun_debrief: bool = True


class ChapterContentPatch(BaseModel):
    content: str = Field(default="", max_length=500_000)


def register_draft_routes(router: APIRouter) -> None:
    """挂载章节正文 PATCH / draft/stream 到 dabai 主路由。"""

    @router.patch("/projects/{project_id}/chapters/{chapter_id}")
    def patch_chapter_content(
        project_id: UUID,
        chapter_id: UUID,
        req: ChapterContentPatch,
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> dict:
        """手动保存章节正文（微调后落库，不触发写后质检/复盘）。"""
        project = _owned_or_404(db, project_id, user)
        ch = (
            db.query(DabaiChapterOutline)
            .filter(DabaiChapterOutline.id == chapter_id,
                    DabaiChapterOutline.project_id == project.id)
            .first()
        )
        if not ch:
            raise HTTPException(status_code=404, detail="章节不存在")
        text = (req.content or "").strip()
        ch.content = text
        ch.status = "written" if text else "planned"
        db.commit()
        return {"id": str(ch.id), "word_count": len(text), "status": ch.status}

    @router.post("/projects/{project_id}/chapters/{chapter_id}/draft/stream")
    async def draft_chapter_stream(
        project_id: UUID,
        chapter_id: UUID,
        req: WriteRequest,
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> StreamingResponse:
        """流式写一章正文（前情 + 写前导演单 + 分场 + 五拍正文），完成后落库。"""
        project = _owned_or_404(db, project_id, user)
        ch = (
            db.query(DabaiChapterOutline)
            .filter(DabaiChapterOutline.id == chapter_id,
                    DabaiChapterOutline.project_id == project.id)
            .first()
        )
        if not ch:
            raise HTTPException(status_code=404, detail="章节不存在")

        block_reason = dabai_chapter_generate_block_reason(db, project.id, ch)
        if block_reason:
            raise HTTPException(status_code=400, detail=block_reason)

        prose_req = ProseWriteRequest(**req.model_dump())

        async def gen():
            try:
                async for evt in run_prose_pipeline(db, project, ch, prose_req, user):
                    yield _sse(evt)
            except (LabPreWarnError, LabScenePlanError) as exc:
                logger.error("dabai 写前阶段中止 chapter=%s：%s", chapter_id, exc)
                yield _sse({"event": "error", "stage": "pre_write", "message": str(exc)})
            except Exception as exc:  # noqa: BLE001
                logger.error("dabai 正文流式异常 chapter=%s：%s", chapter_id, exc)
                yield _sse({"event": "error", "message": str(exc)})

        return StreamingResponse(
            gen(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
