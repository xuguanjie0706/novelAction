"""
draft_routes.py — 章节起笔 / 续写相关 AI 路由

资源边界：本模块仅负责「章节正文生成」类端点（draft-assist/stream、gated-draft-stream
已移至 gated_draft_routes.py、scene-plan）。质检、复盘、记忆等业务在各自模块。

公共辅助函数 `_build_draft_context` 被 gated_draft_routes 复用；
修改此函数时须同步确认 gated 端点行为不变。
"""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, Character, MemoryChunk, OutlineNode, Project, QualityDebt, StoryLine, WorldSetting
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
from app.schemas.scene import ScenePlanRequest, ScenePlanResponse
from app.models import Scene
from app.routers.ai.text_utils import plain_text, strip_tail_meta_lines, truncate

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# 共享上下文构建器
# ═══════════════════════════════════════════════════════════════

def _build_draft_context(
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

    @returns 包含所有 draft_assist_stream kwargs 所需字段的字典：
        chapter_title, outline_hook, outline_summary, outline_conflict,
        outline_highlight, outline_foreshadow, outline_power_milestone,
        outline_emotional_tone, story_day, chapter_manifest, prev_chapter_tail,
        world_summary, character_summary, storyline_summary, memory_summary,
        existing_content, premise, continuity_context, chapter_index_context,
        quality_debt_context, writing_brief_context, plot_dossier_context,
        word_target, phase, positioning, genre, pov_character_name,
        character_screen_time
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

    involved_ids: set = set()
    if outline_node and outline_node.involved_character_ids:
        involved_ids = set(str(cid) for cid in (outline_node.involved_character_ids or []))

    def _char_skill_names(known_skills) -> str:
        if not known_skills:
            return ""
        skill_limit = 10 if large_context else 3
        names = [
            sk.get("skill_name", "") if isinstance(sk, dict) else str(sk)
            for sk in known_skills[:skill_limit]
        ]
        return "、".join(n for n in names if n)

    chapter_manifest_names: list[str] = []
    if involved_ids:
        priority = [c for c in characters if str(c.id) in involved_ids]
        display_chars = priority
        chapter_manifest_names = [c.name for c in priority]
    else:
        display_chars = characters if large_context else characters[:6]

    char_lines = []
    for c in display_chars:
        parts = [f"{c.name}（{c.role}"]
        if large_context and c.alias:
            parts.append(f"别名:{c.alias}")
        if c.current_realm:
            parts.append(f"境界:{c.current_realm}")
        if large_context and c.realm_rank is not None:
            parts.append(f"境界序号:{c.realm_rank}")
        if c.current_location:
            parts.append(f"位置:{c.current_location}")
        if c.current_status and c.current_status != "alive":
            parts.append(f"状态:{c.current_status}")
        skills_str = _char_skill_names(c.known_skills)
        if skills_str:
            parts.append(f"技能:[{skills_str}]")
        parts.append(f"）性格:{(c.personality or '')[:40]}")
        if c.motivation:
            parts.append(f"动机:{truncate(c.motivation, 180 if large_context else 30)}")
        if large_context and c.values:
            parts.append(f"价值观:{truncate(c.values, 180)}")
        if large_context and c.fear:
            parts.append(f"恐惧:{truncate(c.fear, 140)}")
        if large_context and c.secrets:
            parts.append(f"秘密:{truncate(c.secrets, 180)}")
        if large_context and c.known_skills:
            parts.append(f"技能明细:{json.dumps(c.known_skills, ensure_ascii=False)[:1200]}")
        if large_context and c.owned_items:
            parts.append(f"持有物:{json.dumps(c.owned_items, ensure_ascii=False)[:1200]}")
        char_lines.append("".join(parts))

    char_summary = "\n".join(char_lines) if large_context else " | ".join(char_lines)

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

    mem_rows_draft = (
        db.query(MemoryChunk, Chapter)
        .outerjoin(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(MemoryChunk.project_id == project_id)
        .order_by(func.coalesce(Chapter.sort_order, MemoryChunk.chapter_number, -1).desc())
        .limit(80 if large_context else 12)
        .all()
    )
    if large_context:
        memory_summary = "\n".join(
            f"- 第{display_chapter_number(ch.title, ch.sort_order) if ch is not None else (m.chapter_number or '?')}章 "
            f"{m.title or m.memory_type}: {truncate(m.content, 600)}"
            for m, ch in mem_rows_draft
        )
    else:
        memory_summary = " | ".join(
            f"{m.title or m.memory_type}: {m.content[:60]}" for m, _ch in mem_rows_draft
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

    # ── 卷阶段（phase）解析 ─────────────────────────────────────────────
    phase_value: str | None = None
    if outline_node is not None:
        phase_value = getattr(outline_node, "phase", None)
        if not phase_value:
            phase_value = (outline_node.extra or {}).get("phase")
        if not phase_value and outline_node.parent_id is not None:
            volume = db.query(OutlineNode).filter(OutlineNode.id == outline_node.parent_id).first()
            if volume is not None:
                phase_value = getattr(volume, "phase", None) or (volume.extra or {}).get("phase")

    # ── 立项定位（positioning）：兼容多处来源 ──────────────────────────
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

    # P2-W5-2 提取戏份预算与强制 POV
    pov_character_name = ""
    character_screen_time = {}
    if outline_node:
        if outline_node.pov_character:
            pov_character_name = outline_node.pov_character.name
        character_screen_time = outline_node.character_screen_time or {}

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

    ctx = _build_draft_context(db, project_id, chapter, project, large_context)

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

    stream_log_ctx = {"project_id": str(project_id), "chapter_id": str(req.chapter_id)}

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        try:
            async for chunk in svc.draft_assist_stream(
                **ctx,
                user_prompt=user_prompt_str,
                replace_existing=req.replace_existing,
                stream_log_context=stream_log_ctx,
            ):
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ═══════════════════════════════════════════════════════════════
# P2-W5-1：三层调度之分场计划（Scene Plan）
# ═══════════════════════════════════════════════════════════════

@router.post("/scene-plan", response_model=ScenePlanResponse)
async def scene_plan_endpoint(
    project_id: str,
    req: ScenePlanRequest,
    db: Session = Depends(get_db),
):
    """
    章纲 → 分场（Scene Plan）
    输入：OutlineNode 或 Chapter 的摘要
    输出：结构化 4-8 场计划（POV、目标、冲突、转折、钩子、字数预算等）
    供前端展示、分场微调、后续逐场生成正文使用。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    chars = db.query(Character).filter(Character.project_id == project_id).limit(12).all()
    existing_characters = [{"id": str(c.id), "name": c.name, "role": c.role} for c in chars]

    prev_directives = ""
    if req.outline_node_id:
        node = db.query(OutlineNode).filter(OutlineNode.id == req.outline_node_id).first()
        if node and node.extra:
            dirs = node.extra.get("directives_from_prev") or []
            if dirs:
                prev_directives = "; ".join([
                    d.get("patch", {}).get("adjust_pacing", "") or d.get("reason", "")
                    for d in dirs[-2:]
                ])

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    result = await svc.scene_plan(
        chapter_title=req.chapter_title or "未命名章节",
        chapter_summary=req.chapter_summary or "",
        genre=req.genre or project.genre or "玄幻",
        positioning=(project.extra or {}).get("positioning") if hasattr(project, "extra") else None,
        existing_characters=existing_characters,
        prev_directives=prev_directives,
        model_profile=req.model_profile,
        word_target=2200,
    )

    scenes = result.get("scenes", [])
    return {
        "scenes": scenes,
        "total_word_budget": result.get("total_word_budget", 2200),
        "notes": result.get("notes", ""),
    }
