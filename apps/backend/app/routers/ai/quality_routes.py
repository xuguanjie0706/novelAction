from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, Character, Foreshadow, MemoryChunk, OutlineNode, Project, StoryLine, WorldSetting, PowerSystem
from app.services.ai_service import AIService
from app.routers.ai.context import (
    build_chapter_index_context,
    build_continuity_context,
    build_plot_dossier_context,
    format_world_setting_context,
)
from app.routers.ai.quality_debt import sync_quality_debts
from app.routers.ai.schemas import QualityCheckRequest

router = APIRouter()


class PreWriteWarningRequest(BaseModel):
    chapter_plan_summary: str          # 本章五要素或写作计划摘要
    chapter_number: int = 0            # 当前章节号（用于筛选逾期伏笔）
    model_profile: str = "local"
    llm_provider_id: Optional[str] = None


@router.post("/quality-check")
async def quality_check(
    project_id: str,
    req: QualityCheckRequest,
    db: Session = Depends(get_db),
):
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    large_context = req.model_profile == "gemini"

    memory_query = (
        db.query(MemoryChunk)
        .outerjoin(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(MemoryChunk.project_id == project_id)
        .order_by(func.coalesce(Chapter.sort_order, MemoryChunk.chapter_number, 0).asc())
    )
    memories = memory_query.limit(200 if large_context else 50).all()

    settings = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id
    ).all()

    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()

    def _skill_names(known_skills) -> str:
        if not known_skills:
            return "无"
        names = []
        for sk in known_skills[:5]:
            if isinstance(sk, dict):
                names.append(sk.get("skill_name", ""))
            else:
                names.append(str(sk))
        return "、".join(n for n in names if n) or "无"

    character_states = [
        f"{c.name}：境界={c.current_realm or '未知'}，"
        f"位置={c.current_location or '未知'}，"
        f"状态={c.current_status or 'alive'}，"
        f"已知技能=[{_skill_names(c.known_skills)}]"
        for c in characters
    ]

    active_storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["active", "climax"])
    ).all()
    storylines_context = [
        f"{s.name}（{s.line_type}，{s.status}）：{s.core_conflict or s.description or ''}"
        for s in active_storylines
    ]

    power_systems = db.query(PowerSystem).filter(
        PowerSystem.project_id == project_id
    ).all()
    power_systems_summary = []
    for ps in power_systems:
        if large_context:
            levels = []
            for level in (ps.levels or []):
                if isinstance(level, dict):
                    rank = level.get("rank")
                    name = level.get("name") or ""
                    requirement = level.get("requirement") or level.get("description") or ""
                    levels.append(f"{rank}.{name}({requirement})" if rank else f"{name}({requirement})")
                else:
                    levels.append(str(level))
            rules = ps.special_rules or ps.breakthrough_condition or ps.description or ""
            power_systems_summary.append(
                f"{ps.name}：等级={' > '.join(levels) or '未知'}；"
                f"主角当前={ps.protagonist_current_rank or '未知'}；规则={rules}"
            )
        else:
            highest_level = "未知"
            if ps.levels:
                last_level = ps.levels[-1]
                if isinstance(last_level, dict):
                    highest_level = last_level.get("name", "") or "未知"
                else:
                    highest_level = str(last_level) or "未知"
            power_systems_summary.append(
                f"{ps.name}：最高境界={highest_level}，主角当前={ps.protagonist_current_rank or '未知'}"
            )

    outline_context = ""
    node: Optional[OutlineNode] = None
    if chapter.outline_node_id:
        node = db.query(OutlineNode).filter(
            OutlineNode.id == chapter.outline_node_id
        ).first()
        if node:
            parts = []
            if node.summary:
                parts.append(f"本章摘要：{node.summary}")
            if large_context and node.hook:
                parts.append(f"开篇钩子：{node.hook}")
            if large_context and node.conflict:
                parts.append(f"核心冲突：{node.conflict}")
            if large_context and node.highlight:
                parts.append(f"章末方向：{node.highlight}")
            if node.power_milestone:
                parts.append(f"实力里程碑：{node.power_milestone}")
            if node.emotional_tone:
                parts.append(f"情感基调：{node.emotional_tone}")
            if node.foreshadows_laid:
                foreshadow_descs = [
                    f.get("description", "") if isinstance(f, dict) else str(f)
                    for f in node.foreshadows_laid[:3]
                ]
                parts.append(f"本章埋下伏笔：{'；'.join(foreshadow_descs)}")
            outline_context = "；".join(parts)

    continuity_context = build_continuity_context(
        db=db,
        project_id=project_id,
        chapter=chapter,
        outline_node=node,
    )
    chapter_index_context = build_chapter_index_context(
        db=db,
        project_id=project_id,
        chapter=chapter,
    )
    plot_dossier_context = build_plot_dossier_context(
        db=db,
        project_id=project_id,
        chapter=chapter,
        large_context=large_context,
    )

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    result = await svc.quality_check(
        chapter_content=chapter.content,
        chapter_title=chapter.title,
        memories=[m.content for m in memories],
        settings_summary=[
            format_world_setting_context(s, content_limit=2400 if large_context else 260)
            for s in settings
        ],
        check_types=req.check_types,
        character_states=character_states,
        storylines_context=storylines_context,
        power_systems_summary=power_systems_summary,
        outline_context=outline_context,
        continuity_context=continuity_context,
        chapter_index_context=chapter_index_context,
        plot_dossier_context=plot_dossier_context,
    )

    chapter.last_quality_score = result.get("overall_score")
    chapter.last_quality_report = result
    chapter.quality_checked_at = func.now()
    sync_quality_debts(db, project_id, chapter, result)
    db.commit()

    return result


@router.post("/pre-write-warning")
async def pre_write_warning(
    project_id: str,
    req: PreWriteWarningRequest,
    db: Session = Depends(get_db),
):
    """
    写前预警：传入本章计划，对照记忆库/连续性账本/伏笔台账，输出潜在矛盾风险。
    供写作页「动笔前」调用，让作者在落笔前发现连续性/伏笔/设定/人物OOC问题。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # 加载记忆
    memories = (
        db.query(MemoryChunk)
        .filter(MemoryChunk.project_id == project_id)
        .order_by(MemoryChunk.chapter_number.asc())
        .limit(40)
        .all()
    )
    memory_chunks = [
        {"title": m.title or "", "content": m.content or "", "memory_type": m.memory_type or "event"}
        for m in memories
    ]

    # 加载未回收伏笔台账
    open_foreshadows = (
        db.query(Foreshadow)
        .filter(Foreshadow.project_id == project_id, Foreshadow.status == "open")
        .order_by(Foreshadow.priority.desc())
        .limit(30)
        .all()
    )
    foreshadow_lines = []
    for f in open_foreshadows:
        code = f.code or "—"
        overdue = ""
        if f.planned_resolve_chapter and req.chapter_number > 0:
            if f.planned_resolve_chapter <= req.chapter_number:
                overdue = "【⚠️已逾期】"
        foreshadow_lines.append(
            f"{overdue}{code} {f.title or ''} | 预计第{f.planned_resolve_chapter or '?'}章回收 | {(f.description or '')[:100]}"
        )
    foreshadow_ledger = "\n".join(foreshadow_lines)

    # 加载人物状态
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    character_states = "\n".join(
        f"{c.name}：境界={c.current_realm or '?'}，位置={c.current_location or '?'}，状态={c.current_status or 'alive'}"
        for c in characters[:12]
    )

    # 取最近连续性账本（从项目 story_core 里读滚动状态）
    story_core = project.story_core if isinstance(project.story_core, dict) else {}
    continuity_state = story_core.get("rolling_continuity_state", "")

    svc = AIService(
        req.model_profile if req.model_profile in ("gemini", "local") else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    result = await svc.pre_write_warning(
        project_title=project.title,
        genre=project.genre or "玄幻",
        chapter_plan_summary=req.chapter_plan_summary,
        memory_chunks=memory_chunks,
        continuity_state=str(continuity_state) if continuity_state else "",
        foreshadow_ledger=foreshadow_ledger,
        character_states=character_states,
    )
    return result
