"""
scene_draft_routes.py — 逐场起草端点（SSE）

资源边界：Scene 三层调度第二层——按单场元数据生成正文并写回 scene.content。
  POST /ai/scene-draft/stream
"""

from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, Character, OutlineNode, Project, Scene
from app.routers.ai.draft_context import build_power_systems_draft_block
from app.routers.ai.gated_draft_helpers import _build_single_location_block
from app.services.ai.context_assembler import assemble_for_scene_draft
from app.services.ai.scene_constraint_builder import build_scene_constraint_block
from app.services.ai_service import AIService
from app.services.embedding_service import semantic_search as _semantic_search

router = APIRouter()


# ── 请求 schema ─────────────────────────────────────────────────

class SceneDraftRequest(BaseModel):
    """
    逐场起草请求。

    Args:
        scene_id: 目标 Scene UUID；从 DB 读取全部分场元数据。
        model_profile: "local" / "gemini"。
        llm_provider_id: 指定 LlmProvider（可选）。
    """
    scene_id: UUID
    model_profile: str = "local"
    llm_provider_id: Optional[UUID] = None


# ── 端点：逐场起草（SSE）────────────────────────────────────────

@router.post("/scene-draft/stream")
async def scene_draft_stream(
    project_id: str,
    req: SceneDraftRequest,
    db: Session = Depends(get_db),
):
    """
    逐场起草（三层调度第二层），SSE 流式输出。

    1. 从 DB 加载 Scene + 关联 OutlineNode + 项目信息；
    2. 查询上一场结尾钩子（order - 1）；
    3. 语义检索 6 条相关记忆作为上下文；
    4. 通过 ``svc.scene_draft_stream()`` 流式生成；
    5. 流结束后将完整正文写回 ``scene.content``，更新 ``status=written``。

    SSE 事件格式：
      ``data: {"text": "..."}``    — 正文 token
      ``data: {"event": "saved", "scene_id": "...", "word_count": N}``
      ``data: [DONE]``
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    scene = db.query(Scene).filter(
        Scene.id == req.scene_id, Scene.project_id == project_id
    ).first()
    if not scene:
        raise HTTPException(404, "Scene not found")

    # 章节摘要（优先从 outline_node 取）
    chapter_title = ""
    chapter_summary = ""
    if scene.outline_node_id:
        node = db.query(OutlineNode).filter(
            OutlineNode.id == scene.outline_node_id
        ).first()
        if node:
            chapter_title = node.title or node.summary or ""
            chapter_summary = node.summary or ""
    if scene.chapter_id and not chapter_title:
        chap = db.query(Chapter).filter(Chapter.id == scene.chapter_id).first()
        if chap:
            chapter_title = chap.title or ""

    # POV 角色名
    pov_name = ""
    if scene.pov_character_id:
        pov_char = db.query(Character).filter(
            Character.id == scene.pov_character_id
        ).first()
        if pov_char:
            pov_name = pov_char.name
    if not pov_name:
        pov_name = "主角"

    # 在场角色名列表
    on_stage_names: list[str] = []
    if scene.characters_on_stage:
        char_rows = db.query(Character.id, Character.name).filter(
            Character.id.in_(scene.characters_on_stage),
            Character.project_id == project_id,
        ).all()
        on_stage_names = [r.name for r in char_rows]

    # 上一场结尾钩子
    prev_hook = ""
    if scene.order > 1 and scene.outline_node_id:
        prev_scene = db.query(Scene).filter(
            Scene.outline_node_id == scene.outline_node_id,
            Scene.order == scene.order - 1,
        ).first()
        if prev_scene and prev_scene.hook:
            prev_hook = prev_scene.hook

    # 语义记忆（6 条）
    memory_snippets: list[str] = []
    query_text = f"{chapter_title} {scene.goal or ''} {scene.conflict or ''}"
    try:
        mems = await _semantic_search(
            db, project_id, query_text.strip(), top_k=6
        )
        memory_snippets = [m.content for m in mems if m.content]
    except Exception:
        pass

    # 感官基准约束块：精确查库（location_id 优先）→ 名称模糊匹配
    location_context = _build_single_location_block(
        db, project_id,
        location_id=scene.location_id,
        location_name=scene.location_name,
    )

    # 场景级投料约束块（从 scene 新字段 + outline_node.extra 读取）
    node_extra: dict | None = None
    if scene.outline_node_id:
        _node = db.query(OutlineNode).filter(
            OutlineNode.id == scene.outline_node_id
        ).first()
        if _node:
            node_extra = _node.extra or {}
    scene_constraint_block = build_scene_constraint_block(scene, node_extra)
    power_systems_context = build_power_systems_draft_block(db, project_id)

    # 注入人物档案/关系/势力/谜题约束
    scene_ctx = assemble_for_scene_draft(db, project_id, scene, project)
    character_context = scene_ctx.get("character_context", "")

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        full_text = ""
        try:
            async for chunk in svc.scene_draft_stream(
                scene_order=scene.order,
                scene_title=scene.title,
                time=scene.time,
                location_name=scene.location_name,
                pov_character=pov_name,
                characters_on_stage=on_stage_names,
                goal=scene.goal or "",
                conflict=scene.conflict or "",
                turn=scene.turn or "",
                hook_to_plant=scene.hook or "",
                word_budget=scene.word_budget or 400,
                pacing=scene.pacing or "mid",
                sensory_focus=scene.sensory_focus or "mixed",
                prev_hook=prev_hook,
                chapter_title=chapter_title,
                chapter_summary=chapter_summary,
                genre=project.genre or "玄幻",
                positioning=(project.extra or {}).get("positioning"),
                memory_snippets=memory_snippets,
                location_context=location_context,
                scene_constraint_block=scene_constraint_block,
                power_systems_context=power_systems_context,
                character_context=character_context,
            ):
                full_text += chunk
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # 流结束：写回 DB
        if full_text:
            scene.content = full_text
            scene.status = "written"
            scene.actual_word_count = len(full_text)
            db.commit()

        yield (
            f"data: {json.dumps({'event': 'saved', 'scene_id': str(scene.id), 'word_count': len(full_text)}, ensure_ascii=False)}\n\n"
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
