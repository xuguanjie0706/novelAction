"""
scene_routes.py — 三层调度 AI 端点

资源边界：本模块负责 Scene 三层调度链路 + 分场计划生成：
  章纲 → 分场持久化 → 逐场起草（SSE）→ 场景缝合 → chapter.content

端点：
  POST /ai/scene-plan             章纲 → 分场计划（仅返回，不持久化；原 draft_routes）
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
from app.models import Chapter, Character, Foreshadow, Location, OutlineNode, Project, ReaderPromise, Scene
from app.routers.ai.gated_draft_helpers import _build_single_location_block
from app.services.ai.chapter_ingredients import (
    build_constraints_prompt_block,
    compute_chapter_ingredients,
)
from app.services.ai.scene_checklist import verify_scenes_after_stitch
from app.services.ai.scene_constraint_builder import build_scene_constraint_block
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

    # 预加载 Location 列表：① 传给 AI 约束 location_name 选取；② 持久化时做名称→ID 匹配
    all_locations = (
        db.query(Location).filter(Location.project_id == project_id)
        .order_by(Location.sort_order.asc()).all()
    )
    known_locations_for_ai = [
        {"name": l.name, "aliases": l.aliases or [], "sensory_signature": l.sensory_signature or ""}
        for l in all_locations
    ]

    def _resolve_location_id(loc_name: str | None) -> UUID | None:
        """精确名 → 别名 → 包含匹配，返回 Location.id 或 None。"""
        if not loc_name:
            return None
        low = loc_name.strip().lower()
        for l in all_locations:
            if l.name.lower() == low:
                return l.id
        for l in all_locations:
            if any(a.lower() == low for a in (l.aliases or [])):
                return l.id
        for l in all_locations:
            if l.name.lower() in low or low in l.name.lower():
                return l.id
        return None

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

    # ── 计算本章投料清单（ChapterIngredients）────────────────────
    # 主动从设定库拉取：故事线推进指令 / 势力着色 / 技能法宝 / 伏笔操作 / 债务标记
    # 结果同时持久化到 node.extra.pre_write_constraints
    chapter_number = node.sort_order or 0
    ingredients = await compute_chapter_ingredients(
        db=db,
        project_id=project_id,
        outline_node_id=str(req.outline_node_id),
        chapter_number=chapter_number,
    )
    constraints_block = build_constraints_prompt_block(ingredients)

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
        known_locations=known_locations_for_ai or None,
        constraints_block=constraints_block or None,
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

        ai_loc_name: str | None = sc.get("location_name") or None
        resolved_loc_id = _resolve_location_id(ai_loc_name)

        # 将投料约束分配到各场景（AI 输出中若有 constraints 字段则优先使用）
        # 降级策略：AI 未输出 constraints 时，第一场承接所有债务标记
        scene_storyline_moves = sc.get("storyline_moves") or None
        scene_debt_flags = sc.get("debt_flags") or None
        scene_foreshadow_ops = sc.get("foreshadow_ops") or None
        scene_faction_color = sc.get("faction_color") or None
        scene_asset_spotlight = sc.get("asset_spotlight") or None

        # 降级：第一场承接所有 critical 债务和 MUST 故事线推进
        if i == 0 and not scene_debt_flags and ingredients.debt_flags:
            scene_debt_flags = [
                {
                    "debt_type": d.debt_type,
                    "description": d.description,
                    "severity": d.severity,
                    "overdue_chapters": d.overdue_chapters,
                }
                for d in ingredients.debt_flags
                if d.severity == "critical"
            ] or None

        if not scene_storyline_moves and ingredients.storyline_moves:
            must_moves = [m for m in ingredients.storyline_moves if m.must_advance]
            if must_moves and i == 0:
                scene_storyline_moves = [
                    {
                        "storyline_id": m.storyline_id,
                        "name": m.name,
                        "line_type": m.line_type,
                        "must_advance": True,
                        "gap_chapters": m.gap_chapters,
                        "suggested_beat": m.suggested_beat,
                    }
                    for m in must_moves
                ]

        # 结构预警：字数预算与角色数量之间的张力检测
        structural_warnings = []
        on_stage_count = len(on_stage_ids)
        budget = int(sc.get("word_budget") or 400)
        if on_stage_count >= 4 and budget <= 1500:
            structural_warnings.append({
                "code": "CROWD",
                "level": "warn",
                "msg": f"{on_stage_count}角色/{budget}字，建议聚焦2-3人或扩大预算",
            })

        scene = Scene(
            project_id=project_id,
            outline_node_id=req.outline_node_id,
            chapter_id=req.chapter_id,
            order=sc.get("order", i + 1),
            title=sc.get("title") or None,
            time=sc.get("time") or None,
            location_id=resolved_loc_id,
            location_name=ai_loc_name,
            pov_character_id=UUID(pov_id) if pov_id else None,
            characters_on_stage=on_stage_ids,
            goal=sc.get("goal") or "",
            conflict=sc.get("conflict") or "",
            turn=sc.get("turn") or "",
            hook=sc.get("hook") or "",
            hook_strength=int(sc.get("hook_strength") or 3),
            word_budget=budget,
            pacing=sc.get("pacing") or "mid",
            sensory_focus=sc.get("sensory_focus") or "mixed",
            status="planned",
            # 约束字段
            storyline_moves=scene_storyline_moves,
            debt_flags=scene_debt_flags,
            foreshadow_ops=scene_foreshadow_ops,
            faction_color=scene_faction_color,
            asset_spotlight=scene_asset_spotlight,
            structural_warnings=structural_warnings or None,
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
                "location_id": str(s.location_id) if s.location_id else None,
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
                # 约束字段（前端用于展示约束标签）
                "storyline_moves": s.storyline_moves,
                "debt_flags": s.debt_flags,
                "foreshadow_ops": s.foreshadow_ops,
                "faction_color": s.faction_color,
                "asset_spotlight": s.asset_spotlight,
                "structural_warnings": s.structural_warnings,
            }
            for s in sorted(saved, key=lambda x: x.order)
        ],
        "total_word_budget": result.get("total_word_budget", req.word_target),
        "notes": result.get("notes", ""),
        # 投料清单摘要（前端债务看板使用）
        "ingredients_summary": {
            "debt_count": len(ingredients.debt_flags),
            "must_advance_count": sum(1 for m in ingredients.storyline_moves if m.must_advance),
            "foreshadow_ops_count": len(ingredients.foreshadow_ops),
        },
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

    # 感官基准约束块：精确查库（location_id 优先）→ 名称模糊匹配
    location_context = _build_single_location_block(
        db, project_id,
        location_id=scene.location_id,
        location_name=scene.location_name,
    )

    # 场景级投料约束块（从 scene 新字段 + outline_node.extra 读取，无需额外查询）
    node_extra: dict | None = None
    if scene.outline_node_id:
        _node = db.query(OutlineNode).filter(
            OutlineNode.id == scene.outline_node_id
        ).first()
        if _node:
            node_extra = _node.extra or {}
    scene_constraint_block = build_scene_constraint_block(scene, node_extra)

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

    # 异步触发场景核验（不阻塞 stitch 响应）
    import asyncio
    svc_for_check = AIService("default", db=db)

    async def _run_checklist():
        try:
            await verify_scenes_after_stitch(
                db=db,
                project_id=project_id,
                outline_node_id=str(req.outline_node_id),
                svc=svc_for_check,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("verify_scenes_after_stitch failed: %s", exc)

    asyncio.create_task(_run_checklist())

    return {
        "word_count": len(stitched),
        "scene_count": len(written),
        "chapter_id": chapter_id_str,
        "content_preview": stitched[:200],
    }


# ═══════════════════════════════════════════════════════════════
# P2-W5-1：分场计划（仅返回，不持久化）
# 从 draft_routes.py 迁入，与三层调度逻辑统一在本模块。
# ═══════════════════════════════════════════════════════════════

from app.schemas.scene import ScenePlanRequest, ScenePlanResponse  # noqa: E402


@router.post("/scene-plan", response_model=ScenePlanResponse)
async def scene_plan_endpoint(
    project_id: str,
    req: ScenePlanRequest,
    db: Session = Depends(get_db),
):
    """
    章纲 → 分场（Scene Plan），仅返回计划，不写入数据库。

    输入：OutlineNode 或 Chapter 的摘要信息。
    输出：结构化 4-8 场计划（POV、目标、冲突、转折、钩子、字数预算等），
    供前端展示、分场微调、后续逐场生成正文使用。
    如需生成并持久化，请使用 POST /ai/scene-plan-save。
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
