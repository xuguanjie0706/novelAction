import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, Character, MemoryChunk, OutlineNode, Project, StoryLine, WorldSetting
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
from app.routers.ai.quality_debt import build_quality_debt_context, pending_quality_debts_for_chapter
from app.routers.ai.schemas import DraftAssistRequest
from app.routers.ai.text_utils import plain_text, strip_tail_meta_lines, truncate

router = APIRouter()


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
        db=db,
        project_id=project_id,
        chapter=chapter,
        outline_node=outline_node,
    )
    chapter_index_context = build_chapter_index_context(
        db=db,
        project_id=project_id,
        chapter=chapter,
    )
    writing_brief_context = build_writing_brief_context(
        db=db,
        project_id=project_id,
        chapter=chapter,
        outline_node=outline_node,
        large_context=large_context,
    )
    plot_dossier_context = build_plot_dossier_context(
        db, project_id, chapter, large_context=large_context
    )
    quality_debt_context = build_quality_debt_context(
        pending_quality_debts_for_chapter(
            db=db,
            project_id=project_id,
            chapter=chapter,
            limit=12 if large_context else 6,
        )
    )

    def _fmt_foreshadows_for_stream(node) -> str:
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

    outline_foreshadow_str = _fmt_foreshadows_for_stream(outline_node)
    story_day_str = (outline_node.extra or {}).get("story_day", "") if outline_node else ""
    if outline_node:
        word_target_val = int(
            (outline_node.expected_words if outline_node.expected_words else None)
            or (outline_node.extra or {}).get("word_estimate")
            or 2300
        )
    else:
        word_target_val = 2300
    chapter_title_str = chapter.title or ""
    outline_hook_str = outline_node.hook or "" if outline_node else ""
    outline_summary_str = outline_node.summary or "" if outline_node else ""
    outline_conflict_str = outline_node.conflict or "" if outline_node else ""
    outline_highlight_str = outline_node.highlight or "" if outline_node else ""
    outline_power_milestone_str = outline_node.power_milestone or "" if outline_node else ""
    outline_emotional_tone_str = outline_node.emotional_tone or "" if outline_node else ""
    premise_str = project.premise or ""
    user_prompt_str = req.user_prompt or ""
    stream_log_ctx = {"project_id": str(project_id), "chapter_id": str(req.chapter_id)}

    # ── 卷阶段（phase）解析 ─────────────────────────────────────────────
    # 章节计划节点优先取自身 phase；缺省则回溯所属卷的 phase（一卷一阶段是常态，
    # 章节级 override 仅在跨阶段过渡章使用）。
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
    # 优先 Project.extra.positioning（Step 0 写入），回退 Project.story_core.positioning
    # （旧版本兼容 / 兜底放置）；都没有则不注入。
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

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        try:
            async for chunk in svc.draft_assist_stream(
                chapter_title=chapter_title_str,
                outline_hook=outline_hook_str,
                outline_summary=outline_summary_str,
                outline_conflict=outline_conflict_str,
                outline_highlight=outline_highlight_str,
                outline_foreshadow=outline_foreshadow_str,
                outline_power_milestone=outline_power_milestone_str,
                outline_emotional_tone=outline_emotional_tone_str,
                story_day=story_day_str,
                chapter_manifest=chapter_manifest_names,
                prev_chapter_tail=prev_tail,
                world_summary=world_summary,
                character_summary=char_summary,
                storyline_summary=storyline_summary,
                memory_summary=memory_summary,
                existing_content=existing_content,
                premise=premise_str,
                user_prompt=user_prompt_str,
                replace_existing=req.replace_existing,
                continuity_context=continuity_context,
                chapter_index_context=chapter_index_context,
                quality_debt_context=quality_debt_context,
                writing_brief_context=writing_brief_context,
                plot_dossier_context=plot_dossier_context,
                word_target=word_target_val,
                phase=phase_value,
                positioning=positioning_value,
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
