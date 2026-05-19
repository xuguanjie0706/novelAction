"""
scene_routes.py — 三层调度 AI 端点

资源边界：本模块仅负责 Scene 三层调度链路：
  章纲 → 分场持久化 → 逐场起草（SSE）→ 场景缝合 → chapter.content

端点：
  POST /ai/scene-plan-save        章纲 → 分场（AI 生成并持久化到 scenes 表）
  POST /ai/scene-draft/stream     逐场起草（SSE；写完自动存回 scene.content）
  POST /ai/scene-stitch           场景缝合（scenes → chapter.content 草稿）
"""

from __future__ import annotations

import json
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, Character, Foreshadow, OutlineNode, Project, ReaderPromise, Scene
from app.services.ai_service import AIService
from app.services.embedding_service import semantic_search as _semantic_search

router = APIRouter()


# ── 请求/响应 schema ────────────────────────────────────────────

class ScenePlanSaveRequest(BaseModel):
    """
    章纲 → 分场持久化请求。

    Args:
        outline_node_id: chapter_plan 节点 UUID；用于读取摘要并关联 scene。
        chapter_id: 已有章节 UUID（可选，生成后自动绑定 scene.chapter_id）。
        word_target: 全章目标字数，分场时按此分配预算（默认 2200）。
        model_profile: "local" / "gemini"。
        llm_provider_id: 指定 LlmProvider（可选）。
    """
    outline_node_id: UUID
    chapter_id: Optional[UUID] = None
    word_target: int = 2200
    model_profile: str = "local"
    llm_provider_id: Optional[UUID] = None


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


class SceneStitchRequest(BaseModel):
    """
    场景缝合请求。

    Args:
        outline_node_id: 用于查找该节点下全部 status=written 场景。
        chapter_id: 目标章节 UUID；非空时将拼接结果写入 chapter.content。
        require_all_written: True 时若存在 planned 场景则报 400（默认 False）。
    """
    outline_node_id: UUID
    chapter_id: Optional[UUID] = None
    require_all_written: bool = False


# ── 辅助：角色名 → UUID 映射 ────────────────────────────────────

def _build_char_map(db: Session, project_id: str) -> dict[str, str]:
    """返回 {name: str(uuid)} 映射，用于分场持久化时解析 pov_character_name。"""
    rows = db.query(Character.id, Character.name).filter(
        Character.project_id == project_id
    ).all()
    return {r.name: str(r.id) for r in rows}


# ── 端点 1：章纲 → 分场（生成 + 持久化）───────────────────────

@router.post("/scene-plan-save")
async def scene_plan_save(
    project_id: str,
    req: ScenePlanSaveRequest,
    db: Session = Depends(get_db),
):
    """
    章纲 → 分场（三层调度第一层）。

    1. 从 outline_node 读取章节摘要/冲突/钩子，从 DB 读人物列表；
    2. 调用 ``svc.scene_plan()`` 生成结构化分场计划；
    3. 将名字字段映射为 Character UUID；
    4. 替换该节点下旧场景，批量入库，返回 SceneRead 列表。

    Returns:
        {"scenes": [...], "total_word_budget": int, "notes": str}
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    node = db.query(OutlineNode).filter(
        OutlineNode.id == req.outline_node_id,
        OutlineNode.project_id == project_id,
    ).first()
    if not node:
        raise HTTPException(404, "OutlineNode not found")

    char_map = _build_char_map(db, project_id)
    chars_for_prompt = [
        {"id": cid, "name": name} for name, cid in char_map.items()
    ]

    # 读取上一章复盘指令（若有）
    prev_directives = ""
    if node.extra:
        dirs = node.extra.get("directives_from_prev") or []
        if dirs:
            prev_directives = "; ".join(
                d.get("patch", {}).get("adjust_pacing", "") or d.get("reason", "")
                for d in dirs[-2:]
            )

    # ── 约束数据：从 DB 拉取，无需额外 AI 调用 ──────────────────
    # 角色当前状态（取有境界/位置信息的角色，最多 6 条）
    char_state_rows = db.query(
        Character.name,
        Character.current_realm,
        Character.current_status,
        Character.current_location,
    ).filter(
        Character.project_id == project_id,
    ).limit(12).all()
    character_states = [
        {
            "name": r.name,
            "current_realm": r.current_realm,
            "current_status": r.current_status,
            "current_location": r.current_location,
        }
        for r in char_state_rows
        if r.current_realm or r.current_status or r.current_location
    ][:6]

    # 未闭合伏笔（priority≥3，按优先级降序，最多 5 条）
    fw_rows = db.query(
        Foreshadow.title, Foreshadow.description, Foreshadow.priority
    ).filter(
        Foreshadow.project_id == project_id,
        Foreshadow.status == "open",
        Foreshadow.priority >= 3,
    ).order_by(Foreshadow.priority.desc()).limit(5).all()
    open_foreshadows = [
        {"title": r.title, "description": r.description, "priority": r.priority}
        for r in fw_rows
    ]

    # 未兑现读者承诺（priority≥3，按优先级降序，最多 4 条）
    rp_rows = db.query(
        ReaderPromise.promise_text, ReaderPromise.promise_type, ReaderPromise.priority
    ).filter(
        ReaderPromise.project_id == project_id,
        ReaderPromise.status == "open",
        ReaderPromise.priority >= 3,
    ).order_by(ReaderPromise.priority.desc()).limit(4).all()
    open_reader_promises = [
        {"promise_text": r.promise_text, "promise_type": r.promise_type, "priority": r.priority}
        for r in rp_rows
    ]

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    result = await svc.scene_plan(
        chapter_title=node.title or node.summary or "未命名章节",
        chapter_summary=(node.summary or "") + (" " + node.conflict if node.conflict else ""),
        genre=project.genre or "玄幻",
        positioning=(project.extra or {}).get("positioning"),
        existing_characters=chars_for_prompt,
        prev_directives=prev_directives,
        model_profile=req.model_profile,
        word_target=req.word_target,
        character_states=character_states or None,
        open_foreshadows=open_foreshadows or None,
        open_reader_promises=open_reader_promises or None,
    )

    # 替换旧场景
    db.query(Scene).filter(
        Scene.project_id == project_id,
        Scene.outline_node_id == req.outline_node_id,
    ).delete(synchronize_session=False)

    saved: list[Scene] = []
    for i, sc in enumerate(result.get("scenes", [])):
        pov_name = sc.get("pov_character_name") or sc.get("pov_character") or ""
        pov_id = char_map.get(pov_name)

        on_stage_ids: list[UUID] = []
        for name in sc.get("characters_on_stage", []):
            uid = char_map.get(name)
            if uid:
                on_stage_ids.append(UUID(uid))

        scene = Scene(
            project_id=project_id,
            outline_node_id=req.outline_node_id,
            chapter_id=req.chapter_id,
            order=sc.get("order", i + 1),
            title=sc.get("title") or None,
            time=sc.get("time") or None,
            location_name=sc.get("location_name") or None,
            pov_character_id=UUID(pov_id) if pov_id else None,
            characters_on_stage=on_stage_ids,
            goal=sc.get("goal") or "",
            conflict=sc.get("conflict") or "",
            turn=sc.get("turn") or "",
            hook=sc.get("hook") or "",
            hook_strength=int(sc.get("hook_strength") or 3),
            word_budget=int(sc.get("word_budget") or 400),
            pacing=sc.get("pacing") or "mid",
            sensory_focus=sc.get("sensory_focus") or "mixed",
            status="planned",
        )
        db.add(scene)
        saved.append(scene)

    db.commit()
    for s in saved:
        db.refresh(s)

    return {
        "scenes": [
            {
                "id": str(s.id),
                "order": s.order,
                "title": s.title,
                "time": s.time,
                "location_name": s.location_name,
                "pov_character_id": str(s.pov_character_id) if s.pov_character_id else None,
                "goal": s.goal,
                "conflict": s.conflict,
                "turn": s.turn,
                "hook": s.hook,
                "hook_strength": s.hook_strength,
                "word_budget": s.word_budget,
                "pacing": s.pacing,
                "sensory_focus": s.sensory_focus,
                "status": s.status,
            }
            for s in sorted(saved, key=lambda x: x.order)
        ],
        "total_word_budget": result.get("total_word_budget", req.word_target),
        "notes": result.get("notes", ""),
    }


# ── 端点 2：逐场起草（SSE）──────────────────────────────────────

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


# ── 端点 3：场景缝合 → chapter.content ─────────────────────────

@router.post("/scene-stitch")
async def scene_stitch(
    project_id: str,
    req: SceneStitchRequest,
    db: Session = Depends(get_db),
):
    """
    场景缝合（三层调度第三层）。

    按 ``order`` 升序拼接同 ``outline_node_id`` 下所有 ``status=written``
    的场景正文，写入目标 Chapter.content 作为可编辑草稿。

    Args:
        req.outline_node_id: 用于定位全部场景。
        req.chapter_id: 写入目标章节；同时更新各 scene.chapter_id。
        req.require_all_written: True 时若有 planned 场景则拒绝。

    Returns:
        {"word_count": N, "scene_count": N, "chapter_id": str|null,
         "content_preview": str（前200字）}

    Raises:
        404: outline_node / chapter 不存在。
        400: require_all_written=True 且存在未完成场景。
        422: 无 written 场景可缝合。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    scenes: list[Scene] = (
        db.query(Scene)
        .filter(
            Scene.project_id == project_id,
            Scene.outline_node_id == req.outline_node_id,
        )
        .order_by(Scene.order.asc())
        .all()
    )
    if not scenes:
        raise HTTPException(422, "No scenes found for this outline_node_id")

    if req.require_all_written:
        unwritten = [s for s in scenes if s.status != "written"]
        if unwritten:
            raise HTTPException(
                400,
                f"{len(unwritten)} scene(s) not yet written: "
                + ", ".join(str(s.id) for s in unwritten),
            )

    written = [s for s in scenes if s.status == "written" and s.content]
    if not written:
        raise HTTPException(422, "No written scenes to stitch")

    stitched = "\n\n".join(s.content for s in written)

    chapter_id_str: Optional[str] = None
    if req.chapter_id:
        chapter = db.query(Chapter).filter(
            Chapter.id == req.chapter_id,
            Chapter.project_id == project_id,
        ).first()
        if not chapter:
            raise HTTPException(404, "Chapter not found")
        chapter.content = stitched
        chapter_id_str = str(chapter.id)

        # 绑定 scene.chapter_id
        for s in written:
            if s.chapter_id is None:
                s.chapter_id = req.chapter_id

        db.commit()

    return {
        "word_count": len(stitched),
        "scene_count": len(written),
        "chapter_id": chapter_id_str,
        "content_preview": stitched[:200],
    }
