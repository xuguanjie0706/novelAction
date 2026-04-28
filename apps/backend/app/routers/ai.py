from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Literal
from uuid import UUID
import json
import re

from app.database import get_db
from app.models import (
    Chapter,
    MemoryChunk,
    Project,
    WorldSetting,
    Character,
    OutlineNode,
    StoryLine,
    PowerSystem,
    ChapterCoherenceReport,
)
from app.schemas import MemoryChunkCreate, MemoryChunkOut
from app.services.ai_service import AIService

router = APIRouter(prefix="/projects/{project_id}/ai", tags=["ai"])


class QualityCheckRequest(BaseModel):
    chapter_id: str
    check_types: List[str] = ["plot", "character", "setting_consistency", "pacing", "hooks", "outline_alignment"]
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class SuggestRequest(BaseModel):
    chapter_id: str
    prompt: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class ChapterCoherenceCheckRequest(BaseModel):
    chapter_ids: List[str]
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class SaveChapterCoherenceReportRequest(BaseModel):
    name: Optional[str] = None
    model_profile: Literal["local", "gemini"] = "local"
    selected_chapter_ids: List[str]
    result: dict


# ── 质检 ──────────────────────────────────────────────
@router.post("/quality-check")
async def quality_check(
    project_id: str,
    req: QualityCheckRequest,
    db: Session = Depends(get_db)
):
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    memories = db.query(MemoryChunk).filter(
        MemoryChunk.project_id == project_id
    ).order_by(MemoryChunk.chapter_number).limit(50).all()

    settings = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id
    ).all()

    # ── 人物状态快照 ──────────────────────────────────────
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

    # ── 活跃故事线 ────────────────────────────────────────
    active_storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["active", "climax"])
    ).all()
    storylines_context = [
        f"{s.name}（{s.line_type}，{s.status}）：{s.core_conflict or s.description or ''}"
        for s in active_storylines
    ]

    # ── 境界体系摘要 ──────────────────────────────────────
    power_systems = db.query(PowerSystem).filter(
        PowerSystem.project_id == project_id
    ).all()
    power_systems_summary = [
        f"{ps.name}：最高境界={ps.levels[-1].get('name','') if ps.levels else '未知'}，主角当前={ps.protagonist_current_rank or '未知'}"
        for ps in power_systems
    ]

    # ── 大纲上下文（本章节点）────────────────────────────
    outline_context = ""
    if chapter.outline_node_id:
        node = db.query(OutlineNode).filter(
            OutlineNode.id == chapter.outline_node_id
        ).first()
        if node:
            parts = []
            if node.summary:
                parts.append(f"本章摘要：{node.summary}")
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

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    result = await svc.quality_check(
        chapter_content=chapter.content,
        chapter_title=chapter.title,
        memories=[m.content for m in memories],
        settings_summary=[f"{s.title}: {s.content or ''}" for s in settings],
        check_types=req.check_types,
        character_states=character_states,
        storylines_context=storylines_context,
        power_systems_summary=power_systems_summary,
        outline_context=outline_context,
    )

    # 缓存质检结果
    chapter.last_quality_score = result.get("overall_score")
    chapter.last_quality_report = result
    from sqlalchemy.sql import func
    chapter.quality_checked_at = func.now()
    db.commit()

    return result


@router.post("/chapter-coherence-check")
async def chapter_coherence_check(
    project_id: str,
    req: ChapterCoherenceCheckRequest,
    db: Session = Depends(get_db),
):
    if len(req.chapter_ids) < 2:
        raise HTTPException(400, "至少选择2个章节进行连贯性检测")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    chapters = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.id.in_(req.chapter_ids),
    ).all()
    if len(chapters) != len(set(req.chapter_ids)):
        raise HTTPException(400, "存在无效章节ID，或章节不属于当前小说")

    chapters = sorted(chapters, key=lambda c: c.sort_order)
    payload = [
        {
            "id": str(c.id),
            "sort_order": c.sort_order,
            "title": c.title,
            "content": c.content or "",
        }
        for c in chapters
    ]

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    result = await svc.chapter_coherence_check(
        project_title=project.title,
        chapters=payload,
    )
    result["selected_chapter_count"] = len(payload)
    result["selected_chapter_ids"] = [p["id"] for p in payload]
    return result


@router.post("/chapter-coherence-reports")
def save_chapter_coherence_report(
    project_id: str,
    req: SaveChapterCoherenceReportRequest,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    if len(req.selected_chapter_ids) < 2:
        raise HTTPException(400, "至少选择2个章节才能保存检测记录")

    chapter_count = len(req.selected_chapter_ids)
    report = ChapterCoherenceReport(
        project_id=project_id,
        name=(req.name or f"连贯性检测（{chapter_count}章）").strip()[:200],
        model_profile=req.model_profile,
        selected_chapter_ids=req.selected_chapter_ids,
        result=req.result or {},
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {
        "id": str(report.id),
        "name": report.name,
        "model_profile": report.model_profile,
        "selected_chapter_ids": report.selected_chapter_ids,
        "result": report.result,
        "created_at": report.created_at,
    }


@router.get("/chapter-coherence-reports")
def list_chapter_coherence_reports(
    project_id: str,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    safe_limit = 1 if limit < 1 else (100 if limit > 100 else limit)
    reports = (
        db.query(ChapterCoherenceReport)
        .filter(ChapterCoherenceReport.project_id == project_id)
        .order_by(ChapterCoherenceReport.created_at.desc())
        .limit(safe_limit)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "model_profile": r.model_profile,
            "selected_chapter_ids": r.selected_chapter_ids or [],
            "result": r.result or {},
            "created_at": r.created_at,
        }
        for r in reports
    ]


# ── AI 建议（流式）─────────────────────────────────────
@router.post("/suggest/stream")
async def suggest_stream(
    project_id: str,
    req: SuggestRequest,
    db: Session = Depends(get_db)
):
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        async for chunk in svc.suggest_stream(
            chapter_content=chapter.content,
            user_prompt=req.prompt
        ):
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 记忆库提取 ────────────────────────────────────────
@router.post("/extract-memory", response_model=List[MemoryChunkOut])
async def extract_memory(
    project_id: str,
    chapter_id: str,
    model_profile: Literal["local", "gemini"] = "local",
    llm_provider_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    svc = AIService(
        "gemini" if model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=llm_provider_id,
    )
    extracted = await svc.extract_memory(
        chapter_content=chapter.content,
        chapter_title=chapter.title,
        chapter_number=chapter.sort_order + 1,
    )

    results = []
    for item in extracted:
        chunk = MemoryChunk(
            project_id=project_id,
            chapter_id=chapter_id,
            chapter_number=chapter.sort_order + 1,
            **item
        )
        db.add(chunk)
        results.append(chunk)
    db.commit()
    for r in results:
        db.refresh(r)
    return results


# ── AI 辅助写作（流式起笔/续写）──────────────────────
class DraftAssistRequest(BaseModel):
    chapter_id: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None
    """作者补充说明：风格、禁忌、情节走向等，会并入提示词"""
    user_prompt: Optional[str] = None
    """为 True 时按「整章重写」生成，不把长正文当作续写衔接"""
    replace_existing: bool = False


@router.post("/draft-assist/stream")
async def draft_assist_stream(
    project_id: str,
    req: DraftAssistRequest,
    db: Session = Depends(get_db)
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

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # ── 大纲节点（可选）──────────────────────────────
    outline_node = None
    if chapter.outline_node_id:
        outline_node = db.query(OutlineNode).filter(
            OutlineNode.id == chapter.outline_node_id
        ).first()

    # ── 世界观设定 ────────────────────────────────────
    settings = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id
    ).all()
    world_summary = " | ".join(
        f"{s.title}: {(s.content or '')[:70]}" for s in settings[:5]
    )

    # ── 人物（含新增状态字段）────────────────────────────
    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()

    # 如果大纲节点标注了出场人物，优先展示这些人物
    involved_ids: set = set()
    if outline_node and outline_node.involved_character_ids:
        involved_ids = set(str(cid) for cid in (outline_node.involved_character_ids or []))

    def _char_skill_names(known_skills) -> str:
        if not known_skills:
            return ""
        names = [
            sk.get("skill_name", "") if isinstance(sk, dict) else str(sk)
            for sk in known_skills[:3]
        ]
        return "、".join(n for n in names if n)

    # 优先出场人物，不够则补全到 6 人
    if involved_ids:
        priority = [c for c in characters if str(c.id) in involved_ids]
        others = [c for c in characters if str(c.id) not in involved_ids]
        display_chars = (priority + others)[:6]
    else:
        display_chars = characters[:6]

    char_lines = []
    for c in display_chars:
        parts = [f"{c.name}（{c.role}"]
        if c.current_realm:
            parts.append(f"境界:{c.current_realm}")
        if c.current_location:
            parts.append(f"位置:{c.current_location}")
        if c.current_status and c.current_status != "alive":
            parts.append(f"状态:{c.current_status}")
        skills_str = _char_skill_names(c.known_skills)
        if skills_str:
            parts.append(f"技能:[{skills_str}]")
        parts.append(f"）性格:{(c.personality or '')[:40]}")
        if c.motivation:
            parts.append(f"动机:{c.motivation[:30]}")
        char_lines.append("".join(parts))

    char_summary = " | ".join(char_lines)

    # ── 活跃故事线（draft 用）────────────────────────────
    active_storylines_draft = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["active", "climax"])
    ).all()
    storyline_summary = "；".join(
        f"{s.name}（{s.line_type}）：{(s.core_conflict or s.description or '')[:60]}"
        for s in active_storylines_draft[:4]
    )

    # ── 记忆库（最近事件）────────────────────────────
    memories = db.query(MemoryChunk).filter(
        MemoryChunk.project_id == project_id
    ).order_by(MemoryChunk.chapter_number.desc()).limit(12).all()
    memory_summary = " | ".join(
        f"{m.title or m.memory_type}: {m.content[:60]}" for m in memories
    )

    # ── 上一章结尾（衔接用）──────────────────────────
    prev_chapter = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.sort_order < chapter.sort_order,
    ).order_by(Chapter.sort_order.desc()).first()

    prev_tail = ""
    if prev_chapter and prev_chapter.content:
        clean = re.sub(r"<[^>]+>", "", prev_chapter.content or "")
        prev_tail = clean[-400:] if len(clean) > 400 else clean

    # ── 当前章节正文（strip HTML）────────────────────
    existing_content = re.sub(r"<[^>]+>", "", chapter.content or "")

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        try:
            async for chunk in svc.draft_assist_stream(
                chapter_title=chapter.title,
                outline_hook=outline_node.hook or "" if outline_node else "",
                outline_summary=outline_node.summary or "" if outline_node else "",
                outline_conflict=outline_node.conflict or "" if outline_node else "",
                outline_highlight=outline_node.highlight or "" if outline_node else "",
                outline_foreshadow=(outline_node.extra or {}).get("foreshadow", "") if outline_node else "",
                outline_power_milestone=outline_node.power_milestone or "" if outline_node else "",
                outline_emotional_tone=outline_node.emotional_tone or "" if outline_node else "",
                prev_chapter_tail=prev_tail,
                world_summary=world_summary,
                character_summary=char_summary,
                storyline_summary=storyline_summary,
                memory_summary=memory_summary,
                existing_content=existing_content,
                premise=project.premise or "",
                user_prompt=req.user_prompt or "",
                replace_existing=req.replace_existing,
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


# ── 章节复盘（写完后批量更新人物状态/故事线进展）────────
class CharacterUpdate(BaseModel):
    character_id: str
    current_realm: Optional[str] = None
    realm_rank: Optional[int] = None
    current_location: Optional[str] = None
    current_status: Optional[str] = None
    add_skill: Optional[dict] = None      # {"skill_id": "...", "skill_name": "...", "mastery": "初学"}
    add_item: Optional[dict] = None       # {"item_id": "...", "item_name": "...", "acquired_chapter": 5}
    remove_item_id: Optional[str] = None  # 失去道具时传 item_id

class StoryLineUpdate(BaseModel):
    storyline_id: str
    storyline_name: Optional[str] = None
    status: Optional[str] = None          # planned/active/climax/resolved/dropped
    append_beat: Optional[str] = None     # 追加到 key_beats 的新节点描述

class ChapterDebriefRequest(BaseModel):
    chapter_id: str
    character_updates: List[CharacterUpdate] = []
    storyline_updates: List[StoryLineUpdate] = []
    notes: Optional[str] = None           # 作者备注，存到 chapter

@router.post("/chapter-debrief")
def chapter_debrief(
    project_id: str,
    req: ChapterDebriefRequest,
    db: Session = Depends(get_db),
):
    """
    章节写完后的「复盘提交」：批量更新人物状态、故事线进展。
    前端在写作页右侧面板提交，避免「写了文章但数据库状态停留在第1章」的空架子问题。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    updated_chars: List[str] = []
    updated_storylines: List[str] = []

    # ── 更新人物状态 ──────────────────────────────────
    for cu in req.character_updates:
        try:
            _ = UUID(str(cu.character_id))
        except Exception:
            # 非法 ID 直接跳过，避免整次复盘 500
            continue

        char = db.query(Character).filter(
            Character.id == cu.character_id,
            Character.project_id == project_id,
        ).first()
        if not char:
            continue

        if cu.current_realm is not None:
            char.current_realm = cu.current_realm
        if cu.realm_rank is not None:
            char.realm_rank = cu.realm_rank
        if cu.current_location is not None:
            char.current_location = cu.current_location
        if cu.current_status is not None:
            char.current_status = cu.current_status

        # 追加新技能
        if cu.add_skill:
            skills = list(char.known_skills or [])
            # 防止重复（相同 skill_id 则更新 mastery）
            existing_ids = {
                s.get("skill_id") for s in skills if isinstance(s, dict)
            }
            if cu.add_skill.get("skill_id") in existing_ids:
                skills = [
                    {**s, "mastery": cu.add_skill.get("mastery", s.get("mastery"))}
                    if isinstance(s, dict) and s.get("skill_id") == cu.add_skill.get("skill_id")
                    else s
                    for s in skills
                ]
            else:
                skills.append(cu.add_skill)
            char.known_skills = skills

        # 追加新道具
        if cu.add_item:
            items = list(char.owned_items or [])
            existing_item_ids = {
                i.get("item_id") for i in items if isinstance(i, dict)
            }
            if cu.add_item.get("item_id") not in existing_item_ids:
                items.append(cu.add_item)
            char.owned_items = items

        # 移除道具
        if cu.remove_item_id:
            char.owned_items = [
                i for i in (char.owned_items or [])
                if not (isinstance(i, dict) and i.get("item_id") == cu.remove_item_id)
            ]

        updated_chars.append(char.name)

    # ── 更新故事线 ────────────────────────────────────
    for su in req.storyline_updates:
        storyline_uuid = None
        try:
            storyline_uuid = UUID(str(su.storyline_id))
        except Exception:
            storyline_uuid = None

        if storyline_uuid:
            sl = db.query(StoryLine).filter(
                StoryLine.id == storyline_uuid,
                StoryLine.project_id == project_id,
            ).first()
        elif su.storyline_name:
            # AI 偶发返回 name/key 而不是 UUID；按名称兜底匹配
            sl = db.query(StoryLine).filter(
                StoryLine.name == su.storyline_name,
                StoryLine.project_id == project_id,
            ).first()
        else:
            continue

        if not sl:
            continue

        if su.status is not None:
            sl.status = su.status
        if su.append_beat:
            beats = list(sl.key_beats or [])
            beats.append({
                "chapter": chapter.sort_order + 1,
                "chapter_title": chapter.title,
                "beat": su.append_beat,
            })
            sl.key_beats = beats

        updated_storylines.append(sl.name)

    # ── 保存作者备注到章节 ────────────────────────────
    if req.notes:
        chapter.summary = (chapter.summary or "") + f"\n[复盘备注] {req.notes}"

    db.commit()

    return {
        "ok": True,
        "updated_characters": updated_chars,
        "updated_storylines": updated_storylines,
        "message": f"已更新 {len(updated_chars)} 个人物状态、{len(updated_storylines)} 条故事线",
    }


# ── 自动复盘提取（AI 读章节 → 建议人物/故事线更新）────────
class AutoDebriefRequest(BaseModel):
    chapter_id: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None

@router.post("/auto-debrief")
async def auto_debrief(
    project_id: str,
    req: AutoDebriefRequest,
    db: Session = Depends(get_db),
):
    """
    AI 读取章节正文，对照当前人物状态和故事线，
    提取本章发生的状态变化建议。结果仅供前端预填，
    不直接写库——需用户确认后调用 /chapter-debrief 提交。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    if not (chapter.content or "").strip():
        return {
            "character_updates": [],
            "storyline_updates": [],
            "summary": "章节内容为空，无法分析",
        }

    # 构建人物状态快照
    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()
    character_states = [
        {
            "id": str(c.id),
            "name": c.name,
            "current_realm": c.current_realm or "",
            "current_location": c.current_location or "",
            "current_status": c.current_status or "alive",
        }
        for c in characters
    ]

    # 构建故事线快照（只取活跃/规划中的）
    storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["planned", "active", "climax"])
    ).all()
    storylines_data = [
        {
            "id": str(s.id),
            "name": s.name,
            "line_type": s.line_type,
            "status": s.status,
            "core_conflict": s.core_conflict or s.description or "",
        }
        for s in storylines
    ]

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    # strip HTML
    import re as _re
    plain_content = _re.sub(r"<[^>]+>", "", chapter.content or "")

    result = await svc.auto_extract_debrief(
        chapter_content=plain_content,
        chapter_title=chapter.title,
        chapter_number=chapter.sort_order + 1,
        character_states=character_states,
        storylines=storylines_data,
    )
    return result


# ── 记忆库查询 ────────────────────────────────────────
@router.get("/memory", response_model=List[MemoryChunkOut])
def list_memory(
    project_id: str,
    memory_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(MemoryChunk).filter(MemoryChunk.project_id == project_id)
    if memory_type:
        q = q.filter(MemoryChunk.memory_type == memory_type)
    return q.order_by(MemoryChunk.chapter_number).all()
