"""
draft_routes.py — 章节起笔 / 续写相关 AI 路由

资源边界：本模块仅负责「章节正文生成」类端点（draft-assist/stream）。
- 质检、复盘、记忆等业务在各自模块。
- scene-plan 端点已移入 scene_routes.py。
- 上下文构建 helpers 见 draft_context.py。
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
)
from app.routers.ai.pre_write_for_draft import resolve_pre_write_brief_for_draft

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# 共享上下文构建器（被 draft-assist/stream 与 gated-draft-stream 共享）
# ═══════════════════════════════════════════════════════════════

async def _build_draft_context(
    db: Session,
    project_id: str,
    chapter: Chapter,
    project: Project,
    large_context: bool,
) -> dict:
    """
    组装起笔/续写所需的全部上下文字段，返回 dict。

    被 draft-assist/stream 与 gated-draft-stream 共享调用，避免重复代码。
    调用方保证 chapter 和 project 均已从 DB 加载，large_context 已确定。

    @returns 包含所有 draft_assist_stream kwargs 所需字段的字典。
    @see draft_context.py 中的各 _build_* helper 函数了解各字段的构建逻辑
    """
    outline_node = None
    if chapter.outline_node_id:
        outline_node = db.query(OutlineNode).filter(
            OutlineNode.id == chapter.outline_node_id
        ).first()

    settings = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id
    ).all()
    if large_context:
        world_summary = "\n".join(
            f"- {format_world_setting_context(s, content_limit=2400)}"
            for s in settings
        )
    else:
        world_summary = " | ".join(
            format_world_setting_context(s, content_limit=120).replace("\n", "；")
            for s in settings[:8]
        )

    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()

    char_summary, chapter_manifest_names = _build_character_summary(
        db, project_id, characters, outline_node, chapter, large_context
    )

    active_statuses = ["planned", "active", "climax"] if large_context else ["active", "climax"]
    active_storylines_draft = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(active_statuses)
    ).order_by(StoryLine.sort_order).all()
    if large_context:
        storyline_summary = "\n".join(
            f"- {s.name}（{s.line_type}/{s.status}）："
            f"{truncate(s.core_conflict or s.description, 500)}；"
            f"关键节拍={json.dumps(s.key_beats or [], ensure_ascii=False)[:1600]}"
            for s in active_storylines_draft
        )
    else:
        storyline_summary = "；".join(
            f"{s.name}（{s.line_type}）：{(s.core_conflict or s.description or '')[:60]}"
            for s in active_storylines_draft[:4]
        )

    # 语义记忆检索（outline 五要素为 query）+ 时序锚定
    _mem_query = " ".join(filter(None, [
        outline_node.summary if outline_node else None,
        outline_node.conflict if outline_node else None,
        outline_node.highlight if outline_node else None,
    ])) or chapter.title or ""

    _semantic_top_k = 74 if large_context else 10
    _merged, memory_summary, _rag_log, rag_retrieval_snapshot = await retrieve_and_log_draft_context(
        db,
        project_id=project_id,
        chapter_id=chapter.id,
        query=_mem_query,
        top_k_semantic=_semantic_top_k,
        max_chapter=chapter.sort_order,
        recency_limit=6,
        large_context=large_context,
        commit=False,
    )

    prev_chapter = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.sort_order < chapter.sort_order,
    ).order_by(Chapter.sort_order.desc()).first()

    prev_tail = ""
    if prev_chapter and prev_chapter.content:
        prev_plain = plain_text(prev_chapter.content)
        prev_body, _ = split_plain_manuscript_and_index_block(prev_plain)
        base_prev = prev_body.strip() if prev_body.strip() else prev_plain
        clean = strip_tail_meta_lines(base_prev)
        prev_limit = 3000 if large_context else 400
        prev_tail = clean[-prev_limit:] if len(clean) > prev_limit else clean

    existing_content = plain_text(chapter.content)
    narr_existing, _ = split_plain_manuscript_and_index_block(existing_content)
    if narr_existing.strip():
        existing_content = narr_existing.strip()

    # 卷阶段（phase）解析
    phase_value: str | None = None
    if outline_node is not None:
        phase_value = getattr(outline_node, "phase", None)
        if not phase_value:
            phase_value = (outline_node.extra or {}).get("phase")
        if not phase_value and outline_node.parent_id is not None:
            volume = db.query(OutlineNode).filter(OutlineNode.id == outline_node.parent_id).first()
            if volume is not None:
                phase_value = getattr(volume, "phase", None) or (volume.extra or {}).get("phase")

    phase_lower = (phase_value or "").strip().lower() if phase_value else ""
    is_opening = phase_lower in ("opening", "开局期", "新手村")

    continuity_context = build_continuity_context(
        db=db, project_id=project_id, chapter=chapter, outline_node=outline_node,
    )
    chapter_index_context = build_chapter_index_context(
        db=db, project_id=project_id, chapter=chapter,
    )
    writing_brief_context = build_writing_brief_context(
        db=db, project_id=project_id, chapter=chapter,
        outline_node=outline_node, large_context=large_context,
    )

    # 卷内章节进度感（本卷第X/Y章）
    _vol_progress_hint = ""
    if outline_node and outline_node.parent_id:
        try:
            _vol_chapter_count = (
                db.query(OutlineNode)
                .filter(
                    OutlineNode.project_id == project_id,
                    OutlineNode.parent_id == outline_node.parent_id,
                    OutlineNode.node_type == "chapter_plan",
                )
                .count()
            )
            if _vol_chapter_count > 0:
                _vol_ch_idx = (outline_node.sort_order or 0) + 1
                _denom = max(_vol_chapter_count, _vol_ch_idx)
                _vol_progress_hint = (
                    f"\n【卷内章节进度】本卷第 {_vol_ch_idx}/{_denom} 章"
                    f"（{round(_vol_ch_idx / _denom * 100)}%）"
                    f" — 节奏应与当前位置匹配，勿过早/过晚高潮"
                )
        except Exception:
            pass
    if _vol_progress_hint:
        writing_brief_context = writing_brief_context + _vol_progress_hint

    if is_opening:
        plot_dossier_context = ""
        quality_debt_context = ""
    else:
        plot_dossier_context = build_plot_dossier_context(
            db, project_id, chapter, large_context=large_context
        )
        quality_debt_context = build_quality_debt_context(
            pending_quality_debts_for_chapter(
                db=db, project_id=project_id, chapter=chapter,
                limit=12 if large_context else 6,
            )
        )

    def _fmt_foreshadows(node) -> str:
        if not node:
            return ""
        laid = node.foreshadows_laid or []
        resolved = node.foreshadows_resolved or []
        parts = []
        if laid:
            descs = [
                (f.get("description", "") if isinstance(f, dict) else str(f))
                for f in laid[:3]
            ]
            parts.append("埋[" + "；".join(d for d in descs if d) + "]")
        if resolved:
            descs = [
                (f.get("description", "") if isinstance(f, dict) else str(f))
                for f in resolved[:3]
            ]
            parts.append("收[" + "；".join(d for d in descs if d) + "]")
        if not parts:
            legacy = (node.extra or {}).get("foreshadow", "")
            if legacy:
                return legacy
        return "  ".join(parts)

    story_day_str = (outline_node.extra or {}).get("story_day", "") if outline_node else ""
    if outline_node:
        word_target_val = int(
            (outline_node.expected_words if outline_node.expected_words else None)
            or (outline_node.extra or {}).get("word_estimate")
            or 2300
        )
    else:
        word_target_val = 2300

    # 立项定位（positioning）
    positioning_value: dict | None = None
    project_extra = getattr(project, "extra", None) or {}
    if isinstance(project_extra, dict):
        pos = project_extra.get("positioning")
        if isinstance(pos, dict) and pos:
            positioning_value = pos
    if positioning_value is None:
        story_core = getattr(project, "story_core", None) or {}
        if isinstance(story_core, dict):
            pos = story_core.get("positioning")
            if isinstance(pos, dict) and pos:
                positioning_value = pos

    # 戏份预算与强制 POV
    pov_character_name = ""
    character_screen_time = {}
    if outline_node:
        if outline_node.pov_character:
            pov_character_name = outline_node.pov_character.name
        character_screen_time = outline_node.character_screen_time or {}

    # Bootstrap Step 14 一致性矛盾
    _issues_block = _build_consistency_issues_block(
        project_extra=project_extra if isinstance(project_extra, dict) else {},
        manifest_names=chapter_manifest_names,
    )
    if _issues_block:
        continuity_context = continuity_context + _issues_block

    # 爽点结算章硬约束
    _face_slap = (positioning_value or {}).get("face_slap_pattern") or ""
    _hook_req = _calc_hook_requirement(
        phase=phase_value or "",
        sort_order=chapter.sort_order or 0,
        face_slap_pattern=_face_slap,
    )
    if _hook_req:
        writing_brief_context = writing_brief_context + _hook_req

    # ReaderPromise 写章注入
    reader_promise_context = _build_reader_promise_context(
        db, project_id, chapter.sort_order or 0
    )

    # Scene 蓝图注入
    scene_blueprint = _build_scene_blueprint(db, project_id, chapter, outline_node)

    # 复盘闭环：读取 directives_from_prev
    prev_directives_str = _build_prev_directives(outline_node)

    # 上章读者模拟反馈
    _reader_feedback = _build_reader_feedback_context(db, project_id, prev_chapter)
    if _reader_feedback:
        writing_brief_context = writing_brief_context + _reader_feedback

    # hook_strength 趋势预警
    writing_brief_context = _append_hook_trend_warning(
        db, project_id, chapter.sort_order or 0, writing_brief_context
    )

    # 情绪节律 + 反派行动线（Bootstrap Step 9.5 / 9.8 产物闭合回写章路径）
    _narrative_arc = _build_narrative_arc_context(
        project_extra=project_extra if isinstance(project_extra, dict) else {},
        outline_node=outline_node,
        db=db,
    )
    if _narrative_arc:
        writing_brief_context = writing_brief_context + "\n\n" + _narrative_arc

    # 境界快照：查本章出场人物（优先）或所有人物中有 current_realm 的，构建 {name: realm} dict
    # 仅取 realm 已设定的角色；写章时作为硬约束注入 final_reminder，防境界倒退
    _snap_chars = characters if characters else []
    _snap_ids = set(str(cid) for cid in (outline_node.involved_character_ids or [])) if outline_node else set()
    if _snap_ids:
        _snap_chars = [c for c in _snap_chars if str(c.id) in _snap_ids] or _snap_chars
    realm_snapshot_value: dict = {
        c.name: c.current_realm
        for c in _snap_chars[:8]
        if c.name and (c.current_realm or "").strip()
    }

    return dict(
        chapter_title=chapter.title or "",
        outline_hook=outline_node.hook or "" if outline_node else "",
        outline_summary=outline_node.summary or "" if outline_node else "",
        outline_conflict=outline_node.conflict or "" if outline_node else "",
        outline_highlight=outline_node.highlight or "" if outline_node else "",
        outline_foreshadow=_fmt_foreshadows(outline_node),
        outline_power_milestone=outline_node.power_milestone or "" if outline_node else "",
        outline_emotional_tone=outline_node.emotional_tone or "" if outline_node else "",
        story_day=story_day_str,
        chapter_manifest=chapter_manifest_names,
        prev_chapter_tail=prev_tail,
        world_summary=world_summary,
        character_summary=char_summary,
        storyline_summary=storyline_summary,
        memory_summary=memory_summary,
        existing_content=existing_content,
        premise=project.premise or "",
        continuity_context=continuity_context,
        chapter_index_context=chapter_index_context,
        quality_debt_context=quality_debt_context,
        writing_brief_context=writing_brief_context,
        plot_dossier_context=plot_dossier_context,
        word_target=word_target_val,
        phase=phase_value,
        positioning=positioning_value,
        genre=project.genre or "",
        pov_character_name=pov_character_name,
        character_screen_time=character_screen_time,
        scene_blueprint=scene_blueprint,
        reader_promise_context=reader_promise_context,
        prev_directives=prev_directives_str,
        realm_snapshot=realm_snapshot_value,
        rag_retrieval_log_id=str(_rag_log.id),
        rag_retrieval_snapshot=rag_retrieval_snapshot,
    )


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
    large_context = req.model_profile == "gemini"

    ctx = await _build_draft_context(db, project_id, chapter, project, large_context)
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
