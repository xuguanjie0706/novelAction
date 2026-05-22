import json
import logging
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AiChatMessage, Chapter, Character, Foreshadow, OutlineNode, PowerSystem, Project, StoryLine
from app.services.rag_retrieval_service import (
    patch_rag_log_output,
    retrieve_and_log_suggest_memory,
)
from app.services.ai_service import AIService
from app.services.llm_errors import format_llm_error_message
from app.routers.ai.chat_helpers import chat_context_label, query_chat_messages
from app.routers.ai.context import (
    append_reference_chapters_to_writing_context,
    format_outline_chat_context,
    format_writing_chat_context,
)
from app.routers.ai.schemas import ChatMessageOut, ChatStreamRequest, SuggestRequest
from app.routers.ai.text_utils import truncate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/chat/messages", response_model=List[ChatMessageOut])
def list_chat_messages(
    project_id: str,
    context_type: Literal["outline", "writing", "general"] = "general",
    chapter_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    return query_chat_messages(
        db,
        project_id=project_id,
        context_type=context_type,
        chapter_id=chapter_id,
    ).order_by(AiChatMessage.created_at.asc()).limit(200).all()


@router.post("/chat/stream")
async def chat_stream(
    project_id: str,
    req: ChatStreamRequest,
    db: Session = Depends(get_db),
):
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(400, "请输入对话内容")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    chapter: Optional[Chapter] = None
    context_text = ""
    if req.context_type == "outline":
        outline_nodes = db.query(OutlineNode).filter(
            OutlineNode.project_id == project_id
        ).order_by(OutlineNode.sort_order).all()
        characters = db.query(Character).filter(Character.project_id == project_id).all()
        storylines = db.query(StoryLine).filter(StoryLine.project_id == project_id).order_by(StoryLine.sort_order).all()
        power_systems = db.query(PowerSystem).filter(PowerSystem.project_id == project_id).order_by(PowerSystem.sort_order).all()
        context_text = format_outline_chat_context(
            project=project,
            outline_nodes=outline_nodes,
            characters=characters,
            storylines=storylines,
            power_systems=power_systems,
        )
    elif req.context_type == "writing":
        if not req.chapter_id:
            raise HTTPException(400, "写作对话需要当前章节")
        chapter = db.query(Chapter).filter(
            Chapter.id == req.chapter_id,
            Chapter.project_id == project_id,
        ).first()
        if not chapter:
            raise HTTPException(404, "Chapter not found")
        outline_node = None
        if chapter.outline_node_id:
            outline_node = db.query(OutlineNode).filter(
                OutlineNode.id == chapter.outline_node_id,
                OutlineNode.project_id == project_id,
            ).first()
        prev_chapter = db.query(Chapter).filter(
            Chapter.project_id == project_id,
            Chapter.sort_order < chapter.sort_order,
        ).order_by(Chapter.sort_order.desc()).first()
        context_text = format_writing_chat_context(
            project=project,
            chapter=chapter,
            outline_node=outline_node,
            prev_chapter=prev_chapter,
        )
        context_text = append_reference_chapters_to_writing_context(
            db,
            project_id=project_id,
            anchor_chapter_id=chapter.id,
            additional_chapter_ids=req.additional_chapter_ids,
            base_context=context_text,
        )
    else:
        context_text = "\n".join([
            "【作品】",
            f"标题：{project.title}",
            f"类型：{project.genre or '未设置'}",
            f"一句话创意：{truncate(project.logline, 800) or '未设置'}",
            f"立意/故事核：{truncate(project.premise, 1200) or '未设置'}",
        ])

    existing_messages = query_chat_messages(
        db,
        project_id=project_id,
        context_type=req.context_type,
        chapter_id=req.chapter_id if req.context_type == "writing" else None,
    ).order_by(AiChatMessage.created_at.desc()).limit(12).all()
    chat_history = [
        {"role": item.role, "content": item.content}
        for item in reversed(existing_messages)
    ]

    user_message = AiChatMessage(
        project_id=project_id,
        chapter_id=req.chapter_id if req.context_type == "writing" else None,
        context_type=req.context_type,
        role="user",
        content=prompt,
    )
    db.add(user_message)
    db.commit()

    context_label = chat_context_label(req.context_type, chapter)

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        chunks: list[str] = []
        try:
            async for chunk in svc.chat_stream(
                user_prompt=prompt,
                context_label=context_label,
                context_text=context_text,
                chat_history=chat_history,
            ):
                chunks.append(chunk)
                yield f"data: {json.dumps({'text': chunk})}\n\n"
            assistant_text = "".join(chunks).strip()
            if assistant_text:
                db.add(AiChatMessage(
                    project_id=project_id,
                    chapter_id=req.chapter_id if req.context_type == "writing" else None,
                    context_type=req.context_type,
                    role="assistant",
                    content=assistant_text,
                ))
                db.commit()
        except Exception as exc:
            db.rollback()
            yield f"data: {json.dumps({'error': format_llm_error_message(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/suggest/stream")
async def suggest_stream(
    project_id: str,
    req: SuggestRequest,
    db: Session = Depends(get_db),
):
    """
    AI 写作建议流（SSE），已接入 RAG。

    路由层在调用 AI 服务前自动组装三类上下文：
    1. 语义相关记忆（MemoryChunk）：用 user_prompt + 章节正文前 120 字做 query；
    2. 未收束伏笔（Foreshadow.status == 'open'）：按 priority 降序取前 3 条；
    3. 人物状态摘要：按 realm_rank 降序取前 8 个主要人物。

    上下文以 rag_context 字符串注入 AI 提示词，不影响现有响应格式。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    chapter_content_snapshot = chapter.content or ""
    suggest_prompt = req.prompt
    large_context = req.model_profile == "gemini"

    # ── RAG: 语义记忆检索 ─────────────────────────────────────────────────────
    # query = 作者问题 + 章节正文头部，充分利用问题语义定向召回
    _plain_head = truncate(chapter_content_snapshot, 120)
    _mem_query = f"{suggest_prompt} {_plain_head}".strip()
    _mem_top_k = 12 if large_context else 5

    # ── RAG: 未收束伏笔台账 ──────────────────────────────────────────────────
    _open_foreshadows = (
        db.query(Foreshadow)
        .filter(Foreshadow.project_id == project_id, Foreshadow.status == "open")
        .order_by(Foreshadow.priority.desc())
        .limit(3)
        .all()
    )

    # ── RAG: 主要人物状态 ─────────────────────────────────────────────────────
    _characters = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.realm_rank.desc().nullslast())
        .limit(8)
        .all()
    )

    _mem_chunks: list = []
    _suggest_rag_log = None
    if _mem_query:
        try:
            _mem_chunks, _suggest_rag_log = await retrieve_and_log_suggest_memory(
                db,
                project_id=project_id,
                chapter_id=chapter.id,
                query=_mem_query,
                top_k=_mem_top_k,
                max_chapter=chapter.sort_order,
                rag_context="",
                extra_output={
                    "open_foreshadow_count": len(_open_foreshadows),
                    "character_count": len(_characters),
                },
                commit=False,
            )
        except Exception:
            logger.warning(
                "suggest_stream RAG memory retrieval failed",
                exc_info=True,
                extra={"project_id": str(project_id), "chapter_id": str(chapter.id)},
            )
            _mem_chunks = []

    rag_parts: list[str] = []
    if _mem_chunks:
        mem_lines = [
            f"第{m.chapter_number or '?'}章 {m.title or m.memory_type}: "
            f"{(m.content or '')[:120]}"
            for m in _mem_chunks
        ]
        rag_parts.append("近期情节记忆：\n" + "\n".join(f"  · {l}" for l in mem_lines))

    if _open_foreshadows:
        fore_lines = [
            f"[{f.code or 'F'}] {f.title}"
            + (f"：{(f.description or '')[:80]}" if f.description else "")
            for f in _open_foreshadows
        ]
        rag_parts.append("未收束伏笔：\n" + "\n".join(f"  · {l}" for l in fore_lines))

    if _characters:
        char_lines = [
            f"{c.name}（{c.current_realm or '境界未知'}，{c.current_status or 'alive'}）"
            for c in _characters
        ]
        rag_parts.append("主要人物：" + "、".join(char_lines))

    rag_context = "\n\n".join(rag_parts)

    if _suggest_rag_log is not None:
        patch_rag_log_output(
            db,
            _suggest_rag_log,
            {"rag_context_preview": rag_context[:1200] if rag_context else ""},
            commit=True,
        )

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        async for chunk in svc.suggest_stream(
            chapter_content=chapter_content_snapshot,
            user_prompt=suggest_prompt,
            rag_context=rag_context,
        ):
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
