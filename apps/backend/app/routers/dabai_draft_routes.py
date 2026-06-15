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
from app.services.dabai.draft_stream import dabai_draft_max_tokens
from app.services.dabai.intensity import lab_write_sampling, resolve_dabai_intensity
from app.services.dabai.lab_chapter_gate import dabai_chapter_generate_block_reason
from app.services.dabai.lab_draft_context import build_lab_draft_context_async
from app.services.dabai.lab_draft_trace import (
    build_lab_draft_trace,
    llm_call_context_from_trace,
    log_lab_draft_trace,
)
from app.services.dabai.lab_ledger import build_ledger_block, seed_ledgers
from app.services.dabai.lab_post_write import spawn_post_write_pipeline
from app.services.dabai.lab_pre_warn import (
    LabPreWarnError,
    load_lab_pre_warn,
    pre_warn_stale,
    resolve_lab_pre_warn,
)
from app.services.dabai.lab_prompt_shared import build_location_bridge_block
from app.services.dabai.lab_qc_feedback import (
    build_chapter_qc_feedback_block,
    build_forward_qc_block,
)
from app.services.dabai.lab_qc_patch import QcPatchError, iter_qc_patch_chunks
from app.services.dabai.lab_scene_plan import (
    LabScenePlanError,
    refresh_lab_scene_block,
    resolve_lab_scene_plan,
)
from app.services.dabai.lab_word_budget import chapter_word_target, resolve_prose_word_bounds
from app.services.dabai_write import build_prose_prompt

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
        """流式写一章正文（前情 + 写前导演单 + 五拍正文），完成后落库。"""
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

        draft_ctx = await build_lab_draft_context_async(db, project, ch)
        seed_ledgers(db, project)
        ledger_block = build_ledger_block(db, project, ch)
        replace_existing = bool((ch.content or "").strip())
        intensity = resolve_dabai_intensity(project)
        prior_content = (ch.content or "").strip() if replace_existing else ""
        if req.rewrite_mode == "qc_patch" and not replace_existing:
            raise HTTPException(status_code=400, detail="按质检建议修订需要本章已有正文")
        qc_feedback_block = (
            build_chapter_qc_feedback_block(db, ch) if replace_existing else ""
        )
        # 前序章节质检的「后续章节建议」→ 注入本章正文（首写也注入，非只重写/章纲）
        forward_qc_block = build_forward_qc_block(
            db, project.id, target_chapter=int(ch.chapter_number or 0),
        )
        prev_ch = None
        location_bridge_block = ""
        if (ch.chapter_number or 0) > 1:
            prev_ch = (
                db.query(DabaiChapterOutline)
                .filter(
                    DabaiChapterOutline.project_id == project.id,
                    DabaiChapterOutline.chapter_number == ch.chapter_number - 1,
                )
                .first()
            )
            if prev_ch:
                location_bridge_block = build_location_bridge_block(
                    prev_ch, ch, draft_ctx.prev_tail,
                )

        forced_refresh = False
        if replace_existing and not req.rerun_pre_warn:
            _, stored_pre_warn = load_lab_pre_warn(db, ch.id)
            if pre_warn_stale(stored_pre_warn, draft_ctx.prev_content_hash):
                forced_refresh = True
        rerun_pre = bool(req.rerun_pre_warn or forced_refresh)
        rerun_scene = bool(req.rerun_scene_plan or forced_refresh)

        async def gen():
            chunks: list[str] = []
            pre_warn_block = ""
            pre_warn_result = None
            scene_block = ""
            scene_plan_result = None
            ai = None
            draft_trace = None
            try:
                from app.services.ai.service import AIService
                ai = AIService(profile=req.model_profile, db=db,
                               llm_provider_id=req.llm_provider_id, user_id=user.id)
                if req.rewrite_mode == "qc_patch":
                    try:
                        async for delta in iter_qc_patch_chunks(
                            db, ai, project, ch,
                            prior_content=prior_content,
                            user_instruction=(req.user_instruction or "").strip(),
                        ):
                            chunks.append(delta)
                            yield _sse({"event": "chunk", "delta": delta})
                    except QcPatchError as exc:
                        yield _sse({"event": "error", "message": str(exc)})
                        return
                elif replace_existing:
                    if rerun_pre:
                        yield _sse({"event": "pre_warn_running", "dabai_mode": True,
                                    "forced_refresh": forced_refresh})
                        pre_warn_block, pre_warn_evt, pre_warn_result = await resolve_lab_pre_warn(
                            ai, project, ch, draft_ctx, db=db, ledger_block=ledger_block,
                            replace_existing=True,
                            bridge_evidence=location_bridge_block, strict=True,
                        )
                        yield _sse(pre_warn_evt)
                    else:
                        pre_warn_block, pre_warn_result = load_lab_pre_warn(db, ch.id)
                    if rerun_scene:
                        yield _sse({"event": "scene_plan_running", "dabai_mode": True,
                                    "forced_refresh": forced_refresh})
                        scene_block, scene_evt, scene_plan_result = await resolve_lab_scene_plan(
                            ai, project, ch, draft_ctx, db=db,
                            pre_warn_block=pre_warn_block, ledger_block=ledger_block,
                            pre_warn_result=pre_warn_result, prev_ch=prev_ch,
                            replace_existing=True, strict=True,
                        )
                        yield _sse(scene_evt)
                    else:
                        scene_block, scene_plan_result = refresh_lab_scene_block(
                            db, ch,
                            prev_ch=prev_ch,
                            prev_tail=draft_ctx.prev_tail,
                            pre_warn_result=pre_warn_result,
                        )
                else:
                    yield _sse({"event": "pre_warn_running", "dabai_mode": True})
                    pre_warn_block, pre_warn_evt, pre_warn_result = await resolve_lab_pre_warn(
                        ai, project, ch, draft_ctx, db=db, ledger_block=ledger_block,
                        bridge_evidence=location_bridge_block, strict=True,
                    )
                    yield _sse(pre_warn_evt)
                    yield _sse({"event": "scene_plan_running", "dabai_mode": True})
                    scene_block, scene_evt, scene_plan_result = await resolve_lab_scene_plan(
                        ai, project, ch, draft_ctx, db=db,
                        pre_warn_block=pre_warn_block, ledger_block=ledger_block,
                        pre_warn_result=pre_warn_result, prev_ch=prev_ch,
                        strict=True,
                    )
                    yield _sse(scene_evt)
                if req.rewrite_mode != "qc_patch":
                    bounds = resolve_prose_word_bounds(scene_plan_result, ch)
                    prose_hi = bounds[2] if bounds else chapter_word_target(ch) + 200
                    system, user_prompt = build_prose_prompt(
                        project, ch,
                        prev_tail=draft_ctx.prev_tail,
                        recent_plot_block=draft_ctx.recent_plot_block,
                        pre_warn_block=pre_warn_block,
                        scene_block=scene_block,
                        scene_plan=scene_plan_result,
                        ledger_block=ledger_block,
                        memory_block=draft_ctx.memory_block,
                        clue_block=draft_ctx.clue_block,
                        panel_block=draft_ctx.panel_block,
                        prev_full_block=draft_ctx.prev_full_block,
                        prev_hook_block=draft_ctx.prev_hook_block,
                        narrative_state_block=draft_ctx.narrative_state_block,
                        char_voice_block=draft_ctx.char_voice_block,
                        pre_warn_result=pre_warn_result,
                        location_bridge_block=location_bridge_block,
                        qc_feedback_block=qc_feedback_block,
                        forward_qc_block=forward_qc_block,
                        replace_existing=replace_existing,
                        prior_content=prior_content,
                        user_instruction=(req.user_instruction or "").strip(),
                        intensity=intensity,
                    )
                    draft_trace = build_lab_draft_trace(
                        project=project,
                        ch=ch,
                        ctx=draft_ctx,
                        prev_ch=prev_ch,
                        location_bridge_block=location_bridge_block,
                        pre_warn_result=pre_warn_result,
                        scene_block=scene_block,
                        replace_existing=replace_existing,
                        rerun_pre_warn=bool(replace_existing and rerun_pre),
                        rerun_scene_plan=bool(replace_existing and rerun_scene),
                        user_instruction=(req.user_instruction or "").strip(),
                    )
                    log_lab_draft_trace(draft_trace, phase="assembly")
                    write_sampling = lab_write_sampling(
                        intensity, replace_existing=replace_existing,
                    )
                    async for delta in ai._stream_ai(
                        system, user_prompt, task="dabai.write",
                        max_tokens=dabai_draft_max_tokens(prose_hi),
                        sampling=write_sampling,
                        context=llm_call_context_from_trace(draft_trace),
                    ):
                        if not delta:
                            continue
                        chunks.append(delta)
                        yield _sse({"event": "chunk", "delta": delta})
            except (LabPreWarnError, LabScenePlanError) as exc:
                logger.error("dabai 写前阶段中止 chapter=%s：%s", chapter_id, exc)
                yield _sse({"event": "error", "stage": "pre_write", "message": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001
                logger.error("dabai 正文流式异常 chapter=%s：%s", chapter_id, exc)
                yield _sse({"event": "error", "message": str(exc)})
                return
            ch.content = "".join(chunks)
            ch.status = "written"
            db.commit()
            if draft_trace is not None:
                draft_trace["output_head_preview"] = (ch.content or "")[:160]
                log_lab_draft_trace(draft_trace, phase="done")
            yield _sse({"event": "done", "chapter_id": str(chapter_id),
                        "word_count": len(ch.content)})
            events = spawn_post_write_pipeline(
                project.id, ch.id,
                model_profile=req.model_profile,
                llm_provider_id=req.llm_provider_id, user_id=user.id,
                run_quality=req.rerun_quality,
                run_debrief=req.rerun_debrief,
            )
            while True:
                evt = await events.get()
                if evt is None:
                    break
                yield _sse(evt)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
