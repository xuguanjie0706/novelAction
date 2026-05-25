from typing import Literal, Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.embedding_service import semantic_search as _semantic_search
from app.services.rag_retrieval_service import retrieve_and_log_pre_write_memory

from app.database import get_db
from app.models import (
    Chapter,
    Character,
    Foreshadow,
    MemoryChunk,
    OutlineNode,
    PowerSystem,
    PreWriteWarningRecord,
    Project,
    StoryLine,
    WorldSetting,
)
from app.services.ai_service import AIService
from app.services.bootstrap.power_registry import build_draft_power_context_from_db
from app.routers.ai.context import (
    build_chapter_index_context,
    build_continuity_context,
    build_plot_dossier_context,
    format_world_setting_context,
)
from app.routers.ai.quality_debt import sync_quality_debts
from app.routers.ai.schemas import QualityCheckRequest
from app.routers.ai.text_utils import plain_text
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block

router = APIRouter()


class PreWriteWarningRequest(BaseModel):
    chapter_id: str                    # FK chapters.id，用于落库与按章查历史
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
    # 质检：用章节正文前 300 字做语义检索，拉取与本章内容最相关的记忆；max_chapter 防泄漏。
    _qc_plain = ""
    if chapter.content:
        import re as _re
        _qc_plain = _re.sub(r"<[^>]+>", "", chapter.content or "")[:300]
    memories = await _semantic_search(
        db, project_id, _qc_plain or chapter.title or "",
        top_k=200,
        max_chapter=chapter.sort_order,
    )

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

    power_systems_summary = [build_draft_power_context_from_db(db, project_id)]

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
            if node.hook:
                parts.append(f"开篇钩子：{node.hook}")
            if node.conflict:
                parts.append(f"核心冲突：{node.conflict}")
            if node.highlight:
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
            format_world_setting_context(s, content_limit=2400)
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


@router.get("/pre-write-warning/history")
async def pre_write_warning_history(
    project_id: str,
    chapter_id: str,
    db: Session = Depends(get_db),
    limit: int = 30,
):
    """当前章节历次写前预警结果（新→旧），供写作侧栏查阅。"""
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    lim = max(1, min(limit, 50))
    rows = (
        db.query(PreWriteWarningRecord)
        .filter(
            PreWriteWarningRecord.project_id == project_id,
            PreWriteWarningRecord.chapter_id == chapter_id,
        )
        .order_by(PreWriteWarningRecord.created_at.desc())
        .limit(lim)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "chapter_id": str(r.chapter_id),
            "chapter_number": r.chapter_number,
            "chapter_plan_summary": r.chapter_plan_summary or "",
            "model_profile": r.model_profile or "local",
            "result": r.result or {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/pre-write-warning")
async def pre_write_warning(
    project_id: str,
    req: PreWriteWarningRequest,
    db: Session = Depends(get_db),
):
    """
    写前预警：传入本章计划，以「三十年主编」视角输出主角状态锁定、写作简报、必发事件、
    幻觉预防清单和风险扫描，帮助写章 AI 在落笔前建立准确的世界模型。
    结果写入 pre_write_warning_records，可通过 GET history 再次查阅。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    # 加载记忆：语义检索 + RAG 日志（source=pre_write_warning）
    _pw_query = (req.chapter_plan_summary or chapter.title or "").strip()
    _pw_rag_log = None
    if _pw_query:
        _pw_mems, _pw_rag_log = await retrieve_and_log_pre_write_memory(
            db,
            project_id=project_id,
            chapter_id=chapter.id,
            query=_pw_query,
            top_k=40,
            max_chapter=req.chapter_number if req.chapter_number else chapter.sort_order,
            commit=False,
        )
    else:
        _pw_mems = []
    memory_chunks = [
        {"title": m.title or "", "content": m.content or "", "memory_type": m.memory_type or "event"}
        for m in _pw_mems
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

    # 加载人物状态（含技能与持有物）
    characters = db.query(Character).filter(Character.project_id == project_id).all()

    def _skill_names_brief(known_skills) -> str:
        if not known_skills:
            return ""
        names = [
            (sk.get("skill_name", "") if isinstance(sk, dict) else str(sk))
            for sk in known_skills[:6]
        ]
        return "、".join(n for n in names if n)

    def _item_names_brief(owned_items) -> str:
        if not owned_items:
            return ""
        names = [
            (it.get("item_name", "") if isinstance(it, dict) else str(it))
            for it in owned_items[:6]
        ]
        return "、".join(n for n in names if n)

    character_lines = []
    for c in characters[:12]:
        parts = [f"{c.name}：境界={c.current_realm or '?'}，位置={c.current_location or '?'}，状态={c.current_status or 'alive'}"]
        sk = _skill_names_brief(c.known_skills)
        if sk:
            parts.append(f"技能=[{sk}]")
        it = _item_names_brief(c.owned_items)
        if it:
            parts.append(f"持有=[{it}]")
        character_lines.append("，".join(parts))
    character_states = "\n".join(character_lines)

    # 境界体系（多轴全保真）
    power_systems_summary = build_draft_power_context_from_db(db, project_id)

    # 大纲上下文（五要素）
    outline_context = ""
    outline_node = None
    if chapter.outline_node_id:
        outline_node = db.query(OutlineNode).filter(OutlineNode.id == chapter.outline_node_id).first()
        if outline_node:
            parts = []
            if outline_node.summary:
                parts.append(f"概述：{outline_node.summary}")
            if outline_node.hook:
                parts.append(f"开篇钩子：{outline_node.hook}")
            if outline_node.conflict:
                parts.append(f"核心冲突：{outline_node.conflict}")
            if outline_node.highlight:
                parts.append(f"章末方向：{outline_node.highlight}")
            if outline_node.power_milestone:
                parts.append(f"实力里程碑：{outline_node.power_milestone}")
            if outline_node.emotional_tone:
                parts.append(f"情感基调：{outline_node.emotional_tone}")
            outline_context = "\n".join(parts)

    # 章节阶段（phase）
    phase = ""
    if outline_node:
        phase = getattr(outline_node, "phase", None) or (outline_node.extra or {}).get("phase") or ""
    if not phase and outline_node and outline_node.parent_id:
        vol = db.query(OutlineNode).filter(OutlineNode.id == outline_node.parent_id).first()
        if vol:
            phase = getattr(vol, "phase", None) or (vol.extra or {}).get("phase") or ""

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
        power_systems_summary=power_systems_summary,
        outline_context=outline_context,
        phase=phase,
    )

    ch_no = req.chapter_number if req.chapter_number > 0 else (chapter.sort_order or 0)
    profile = req.model_profile if req.model_profile in ("local", "gemini") else "local"
    rec = PreWriteWarningRecord(
        project_id=project.id,
        chapter_id=chapter.id,
        chapter_number=ch_no,
        chapter_plan_summary=req.chapter_plan_summary or "",
        model_profile=profile,
        llm_provider_id=req.llm_provider_id,
        result=result,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    out = dict(result)
    out["record_id"] = str(rec.id)
    if _pw_rag_log is not None:
        out["rag_retrieval_log_id"] = str(_pw_rag_log.id)
    return out


# ═══════════════════════════════════════════════════════════════
# P1-6：读者模拟器 — 让 AI 扮演 5 类典型读者给出章评
# ═══════════════════════════════════════════════════════════════

class ReaderSimulatorRequest(BaseModel):
    chapter_id: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


@router.post("/reader-simulator")
async def reader_simulator(
    project_id: str,
    req: ReaderSimulatorRequest,
    db: Session = Depends(get_db),
):
    """
    读者模拟器：让 AI 同时扮演 5 类典型网文读者，对刚写完的章节给出：
    - 追新型：爽点是否足够？会不会继续追？
    - 考据党：设定/逻辑是否严谨？
    - CP 党：感情线是否甜/虐到位？
    - 爽文党：打脸/升级/装逼是否解气？
    - 剧情党：钩子与反转是否抓人？
    每类返回：评分(1-10) + 一段章评 + “会不会追下一章”的判断。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    plain = plain_text(chapter.content or "")
    narrative, _ = split_plain_manuscript_and_index_block(plain)
    if not narrative.strip():
        narrative = plain

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    result = await svc.reader_simulator(
        chapter_title=chapter.title,
        chapter_content=narrative[:8000],
        genre=project.genre or "玄幻",
    )
    return result
