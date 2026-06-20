"""dabai 实验书架正文写作 SSE 编排薄壳。"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.user import User
from app.services.dabai.intensity import lab_write_sampling, resolve_dabai_intensity
from app.services.dabai.lab_chapter_boundary import build_forward_chapter_boundary_block
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
from app.services.dabai.prose.prompt_assemble import build_prose_prompt

logger = logging.getLogger("dabai.prose.orchestrator")

_CLICHE_QC_RULES = frozenset({"DLB-06", "DB-17"})


class ProseWriteRequest(BaseModel):
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: UUID | None = None
    user_instruction: str = Field(default="", max_length=4000)
    rewrite_mode: Literal["full", "qc_patch"] = "full"
    rerun_pre_warn: bool = False
    rerun_scene_plan: bool = False
    rerun_quality: bool = True
    rerun_debrief: bool = True


def _latest_qc_has_cliche(db: Session, ch_id: UUID) -> bool:
    from app.models.dabai_lab import DabaiQualityReport

    row = (
        db.query(DabaiQualityReport)
        .filter(DabaiQualityReport.chapter_id == ch_id)
        .order_by(DabaiQualityReport.created_at.desc())
        .first()
    )
    if not row or not isinstance(row.report, dict):
        return False
    rep = row.report
    for w in (rep.get("warnings") or []):
        if isinstance(w, dict) and w.get("rule_id") in _CLICHE_QC_RULES:
            return True
    for b in (rep.get("blockers") or []):
        if isinstance(b, dict) and b.get("rule_id") in _CLICHE_QC_RULES:
            return True
    return False


async def run_prose_pipeline(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    req: ProseWriteRequest,
    user: User,
) -> AsyncIterator[dict]:
    """gate → context → prewarn → scene → draft → persist → post_write。"""
    draft_ctx = await build_lab_draft_context_async(db, project, ch)
    seed_ledgers(db, project)
    ledger_block = build_ledger_block(db, project, ch)
    replace_existing = bool((ch.content or "").strip())
    intensity = resolve_dabai_intensity(project)
    prior_content = (ch.content or "").strip() if replace_existing else ""
    qc_feedback_block = build_chapter_qc_feedback_block(db, ch) if replace_existing else ""
    forward_qc_block = build_forward_qc_block(
        db, project.id, target_chapter=int(ch.chapter_number or 0),
    )
    chapter_boundary_block = build_forward_chapter_boundary_block(db, project.id, ch)

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
        if _latest_qc_has_cliche(db, ch.id):
            forced_refresh = True
    rerun_pre = bool(req.rerun_pre_warn or forced_refresh)
    rerun_scene = bool(req.rerun_scene_plan or forced_refresh)

    chunks: list[str] = []
    pre_warn_block = ""
    pre_warn_result = None
    scene_block = ""
    scene_plan_result = None
    draft_trace = None

    from app.services.ai.service import AIService

    ai = AIService(
        profile=req.model_profile, db=db,
        llm_provider_id=req.llm_provider_id, user_id=user.id,
    )

    if req.rewrite_mode == "qc_patch":
        if not replace_existing:
            yield {"event": "error", "message": "按质检建议修订需要本章已有正文"}
            return
        try:
            async for delta in iter_qc_patch_chunks(
                db, ai, project, ch,
                prior_content=prior_content,
                user_instruction=(req.user_instruction or "").strip(),
            ):
                chunks.append(delta)
                yield {"event": "chunk", "delta": delta}
        except QcPatchError as exc:
            yield {"event": "error", "message": str(exc)}
            return
    elif replace_existing:
        if rerun_pre:
            yield {"event": "pre_warn_running", "dabai_mode": True, "forced_refresh": forced_refresh}
            pre_warn_block, pre_warn_evt, pre_warn_result = await resolve_lab_pre_warn(
                ai, project, ch, draft_ctx, db=db, ledger_block=ledger_block,
                replace_existing=True, bridge_evidence=location_bridge_block, strict=True,
            )
            yield pre_warn_evt
        else:
            pre_warn_block, pre_warn_result = load_lab_pre_warn(db, ch.id)
        if rerun_scene:
            yield {"event": "scene_plan_running", "dabai_mode": True, "forced_refresh": forced_refresh}
            scene_block, scene_evt, scene_plan_result = await resolve_lab_scene_plan(
                ai, project, ch, draft_ctx, db=db,
                pre_warn_block=pre_warn_block, ledger_block=ledger_block,
                pre_warn_result=pre_warn_result, prev_ch=prev_ch,
                replace_existing=True, strict=True,
            )
            yield scene_evt
        else:
            scene_block, scene_plan_result = refresh_lab_scene_block(
                db, ch, prev_ch=prev_ch, prev_tail=draft_ctx.prev_tail,
                pre_warn_result=pre_warn_result,
            )
    else:
        yield {"event": "pre_warn_running", "dabai_mode": True}
        pre_warn_block, pre_warn_evt, pre_warn_result = await resolve_lab_pre_warn(
            ai, project, ch, draft_ctx, db=db, ledger_block=ledger_block,
            bridge_evidence=location_bridge_block, strict=True,
        )
        yield pre_warn_evt
        yield {"event": "scene_plan_running", "dabai_mode": True}
        scene_block, scene_evt, scene_plan_result = await resolve_lab_scene_plan(
            ai, project, ch, draft_ctx, db=db,
            pre_warn_block=pre_warn_block, ledger_block=ledger_block,
            pre_warn_result=pre_warn_result, prev_ch=prev_ch, strict=True,
        )
        yield scene_evt

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
            chapter_boundary_block=chapter_boundary_block,
            realm_writing_block=draft_ctx.realm_writing_block,
            replace_existing=replace_existing,
            prior_content=prior_content,
            user_instruction=(req.user_instruction or "").strip(),
            intensity=intensity,
        )
        from app.services.dabai.lab_word_budget import dabai_draft_max_tokens

        from app.services.dabai.prose.beat_contract import beat_similarity, resolve_beats

        contract = resolve_beats(ch, pre_warn_result)
        draft_trace = build_lab_draft_trace(
            project=project, ch=ch, ctx=draft_ctx, prev_ch=prev_ch,
            location_bridge_block=location_bridge_block,
            pre_warn_result=pre_warn_result, scene_block=scene_block,
            replace_existing=replace_existing, rerun_pre_warn=bool(replace_existing and rerun_pre),
            rerun_scene_plan=bool(replace_existing and rerun_scene),
            user_instruction=(req.user_instruction or "").strip(),
            beat_source=contract.source,
            yaqu_similarity=round(
                beat_similarity(ch.yaqu_setup or "", contract.yaqu), 3,
            ),
            opening_policy_mode=(
                "ch1" if int(ch.chapter_number or 0) == 1 else "continuity"
            ),
        )
        log_lab_draft_trace(draft_trace, phase="assembly")
        write_sampling = lab_write_sampling(intensity, replace_existing=replace_existing)
        async for delta in ai._stream_ai(
            system, user_prompt, task="dabai.write",
            max_tokens=dabai_draft_max_tokens(prose_hi),
            sampling=write_sampling,
            context=llm_call_context_from_trace(draft_trace),
        ):
            if delta:
                chunks.append(delta)
                yield {"event": "chunk", "delta": delta}

    ch.content = "".join(chunks)
    ch.status = "written"
    db.commit()
    if draft_trace is not None:
        draft_trace["output_head_preview"] = (ch.content or "")[:160]
        log_lab_draft_trace(draft_trace, phase="done")
    yield {"event": "done", "chapter_id": str(ch.id), "word_count": len(ch.content)}

    events = spawn_post_write_pipeline(
        ch.project_id, ch.id,
        model_profile=req.model_profile,
        llm_provider_id=req.llm_provider_id, user_id=user.id,
        run_quality=req.rerun_quality,
        run_debrief=req.rerun_debrief,
    )
    while True:
        evt = await events.get()
        if evt is None:
            break
        yield evt
