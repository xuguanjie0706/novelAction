from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Literal
import json
import re

from app.database import get_db
from app.models import Chapter, MemoryChunk, Project, WorldSetting, Character, OutlineNode
from app.schemas import MemoryChunkCreate, MemoryChunkOut
from app.services.ai_service import AIService

router = APIRouter(prefix="/projects/{project_id}/ai", tags=["ai"])


class QualityCheckRequest(BaseModel):
    chapter_id: str
    check_types: List[str] = ["plot", "character", "setting_consistency", "pacing", "hooks"]
    model_profile: Literal["local", "gemini"] = "local"


class SuggestRequest(BaseModel):
    chapter_id: str
    prompt: str
    model_profile: Literal["local", "gemini"] = "local"


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

    memories = db.query(MemoryChunk).filter(
        MemoryChunk.project_id == project_id
    ).order_by(MemoryChunk.chapter_number).limit(50).all()

    settings = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id
    ).all()

    svc = AIService("gemini" if req.model_profile == "gemini" else "default", db=db)
    result = await svc.quality_check(
        chapter_content=chapter.content,
        chapter_title=chapter.title,
        memories=[m.content for m in memories],
        settings_summary=[f"{s.title}: {s.content or ''}" for s in settings],
        check_types=req.check_types,
    )

    # 缓存质检结果
    chapter.last_quality_score = result.get("overall_score")
    chapter.last_quality_report = result
    from sqlalchemy.sql import func
    chapter.quality_checked_at = func.now()
    db.commit()

    return result


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

    svc = AIService("gemini" if req.model_profile == "gemini" else "default", db=db)

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
    db: Session = Depends(get_db)
):
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    svc = AIService("gemini" if model_profile == "gemini" else "default", db=db)
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

    # ── 人物 ──────────────────────────────────────────
    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()
    char_summary = " | ".join(
        f"{c.name}（{c.role}，{c.faction or '无门派'}）性格：{(c.personality or '')[:50]} 动机：{(c.motivation or '')[:40]}"
        for c in characters[:5]
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

    svc = AIService("gemini" if req.model_profile == "gemini" else "default", db=db)

    async def event_stream():
        try:
            async for chunk in svc.draft_assist_stream(
                chapter_title=chapter.title,
                outline_hook=outline_node.hook or "" if outline_node else "",
                outline_summary=outline_node.summary or "" if outline_node else "",
                outline_conflict=outline_node.conflict or "" if outline_node else "",
                outline_highlight=outline_node.highlight or "" if outline_node else "",
                outline_foreshadow=(outline_node.extra or {}).get("foreshadow", "") if outline_node else "",
                prev_chapter_tail=prev_tail,
                world_summary=world_summary,
                character_summary=char_summary,
                memory_summary=memory_summary,
                existing_content=existing_content,
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
