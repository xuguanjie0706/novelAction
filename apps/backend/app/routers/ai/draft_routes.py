"""
draft_routes.py — 章节起笔 / 续写相关 AI 路由

资源边界：本模块仅负责「章节正文生成」类端点（draft-assist/stream）。
- 质检、复盘、记忆等业务在各自模块。
- scene-plan 端点已移入 scene_routes.py。
- 上下文构建已迁移至 services/ai/context_assembler.py（分层检索）。
- 公共 _build_draft_context 被 gated_draft_routes 复用；修改时须同步验证 gated 端点行为。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Chapter,
    Character,
    ChapterIndex,
    MemoryChunk,
    OutlineNode,
    Project,
    QualityDebt,
    StoryLine,
    WorldSetting,
)
from app.services.ai_service import AIService
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block
from app.utils.chapter_numbering import display_chapter_number
from app.routers.ai.context import (
    build_chapter_index_context,
    build_continuity_context,
    build_plot_dossier_context,
    build_writing_brief_context,
    format_world_setting_context,
)
from app.routers.ai.quality_debt import (
    build_quality_debt_context,
    pending_quality_debts_for_chapter,
    resolve_chapter_for_quality_debt,
)
from app.routers.ai.schemas import DraftAssistRequest
from app.routers.ai.text_utils import plain_text, strip_tail_meta_lines, truncate
from app.services.rag_retrieval_service import retrieve_and_log_draft_context
from app.routers.ai.draft_helpers import (
    _build_consistency_issues_block,
    _calc_hook_requirement,
    merge_writing_config,
    prewrite_gate_violation,
)
from app.routers.ai.draft_context import (
    _append_hook_trend_warning,
    _build_character_summary,
    _build_narrative_arc_context,
    _build_prev_directives,
    _build_reader_feedback_context,
    _build_reader_promise_context,
    _build_scene_blueprint,
    build_power_systems_draft_block,
)
from app.routers.ai.pre_write_for_draft import resolve_pre_write_brief_for_draft
from app.services.ai.context_assembler import assemble_full

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# 共享上下文构建器（被 draft-assist/stream 与 gated-draft-stream 共享）
# ═══════════════════════════════════════════════════════════════

async def _build_draft_context(
    db: Session,
    project_id: str,
    chapter: Chapter,
    project: Project,
) -> dict:
    """
    组装起笔/续写所需的全部上下文字段，返回 dict。

    被 draft-assist/stream 与 gated-draft-stream 共享调用，避免重复代码。
    调用方保证 chapter 和 project 均已从 DB 加载。

    实现已委托给 context_assembler.assemble_full（分层检索），
    按 OutlineNode 索引过滤，大幅减少 token 消耗（~15万→~3万）。

    @returns 包含所有 draft_assist_stream kwargs 所需字段的字典。
    @see services/ai/context_assembler.py 了解分层检索架构
    """
    return await assemble_full(db, project_id, chapter, project)


# ═══════════════════════════════════════════════════════════════
# 端点：draft-assist/stream（普通起笔/续写，不带质量门控）
# ═══════════════════════════════════════════════════════════════

@router.post("/draft-assist/stream")
async def draft_assist_stream(
    project_id: str,
    req: DraftAssistRequest,
    db: Session = Depends(get_db),
):
    """
    根据章节大纲计划 + 世界观 + 人物 + 记忆库 + 前章结尾，
    流式生成本章起笔或续写建议。
    像一位有 30 年经验的作家：把设定、人物弧、伏笔自然织入正文。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    if req.replace_existing:
        from app.routers.chapters import clear_chapter_rewrite_derivatives
        clear_chapter_rewrite_derivatives(db, project_id, req.chapter_id)
        db.commit()
        db.refresh(chapter)

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    ctx = await _build_draft_context(db, project_id, chapter, project)
    rag_snapshot = ctx.pop("rag_retrieval_snapshot", None)
    rag_log_id = ctx.pop("rag_retrieval_log_id", None)
    db.commit()

    cfg_wm = merge_writing_config(project, None)
    viol = prewrite_gate_violation(
        db, project, chapter, ctx, cfg_wm, req.consistency_issue_ack,
    )
    if viol:
        raise HTTPException(status_code=409, detail=viol)

    user_prompt_str = (req.user_prompt or "").strip()

    if req.focus_quality_debt_id:
        debt = (
            db.query(QualityDebt)
            .filter(
                QualityDebt.project_id == project_id,
                QualityDebt.id == req.focus_quality_debt_id,
            )
            .first()
        )
        if not debt:
            raise HTTPException(404, "Quality debt not found")
        exp_ch = resolve_chapter_for_quality_debt(db, project_id, debt)
        if not exp_ch or str(exp_ch.id) != str(req.chapter_id):
            raise HTTPException(
                400,
                "该质量债务与当前章节不匹配，请打开来源章的写作页后再发起 AI 修复",
            )
        if debt.status != "pending":
            raise HTTPException(400, "仅「待处理」状态的质量债务可使用定向 AI 修复")
        focus_block = (
            "\n\n【本轮首要任务：消除下列单条质量债务】\n"
            f"类型：{debt.issue_type}｜严重度：{debt.severity}\n"
            f"问题：{debt.summary}\n"
        )
        if debt.suggested_fix:
            focus_block += f"建议修正方向：{debt.suggested_fix}\n"
        if debt.author_notes:
            focus_block += f"作者备注（手动修复要点）：{debt.author_notes}\n"
        focus_block += (
            "写作要求：在叙事正文中落实修改，避免口号式敷衍；保持本章大纲节拍与人物口吻；"
            "若整章重写，须保留章末追读钩子。"
        )
        user_prompt_str = (user_prompt_str + focus_block).strip()

    stream_log_ctx = {
        "project_id": str(project_id),
        "chapter_id": str(req.chapter_id),
        "rag_retrieval_log_id": rag_log_id,
    }

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        if rag_snapshot:
            yield f"data: {json.dumps(rag_snapshot, ensure_ascii=False)}\n\n"

        pre_warn_brief_block = ""
        if cfg_wm.get("pre_write_warning_enabled"):
            pre_warn_brief_block, pre_warn_events = await resolve_pre_write_brief_for_draft(
                db,
                chapter=chapter,
                project=project,
                project_id=str(project_id),
                svc=svc,
                enabled=True,
                model_profile=req.model_profile or "local",
                llm_provider_id=str(req.llm_provider_id) if req.llm_provider_id else None,
                persist_record=True,
                reuse_if_exists=bool(req.replace_existing),
            )
            for payload in pre_warn_events:
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        try:
            async for chunk in svc.draft_assist_stream(
                **ctx,
                user_prompt=user_prompt_str,
                replace_existing=req.replace_existing,
                pre_write_brief=pre_warn_brief_block,
                stream_log_context=stream_log_ctx,
            ):
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        warnings = getattr(svc, "_truncation_warnings", None) or []
        if warnings:
            yield f"data: {json.dumps({'event': 'truncation_warning', 'warnings': list(warnings)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
