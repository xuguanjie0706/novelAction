"""
scene_plan_routes.py — 分场计划端点

资源边界：章纲 → 分场（AI 生成并持久化 / 仅返回预览）。
  POST /ai/scene-plan-save  章纲 → 分场（生成 + 持久化到 scenes 表）
  POST /ai/scene-plan       章纲 → 分场（仅返回，不持久化）
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Character, Foreshadow, Location, OutlineNode, Project, ReaderPromise, Scene
from app.schemas.scene import ScenePlanRequest, ScenePlanResponse
from app.services.ai.chapter_ingredients import (
    build_constraints_prompt_block,
    compute_chapter_ingredients,
)
from app.services.ai.context_assembler import assemble_for_scene_plan
from app.services.ai_service import AIService

router = APIRouter()


# ── 请求 schema ─────────────────────────────────────────────────

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


# ── 辅助：角色名 → UUID 映射 ─────────────────────────────────────

def _build_char_map(db: Session, project_id: str) -> dict[str, str]:
    """返回 {name: str(uuid)} 映射，用于分场持久化时解析 pov_character_name。"""
    rows = db.query(Character.id, Character.name).filter(
        Character.project_id == project_id
    ).all()
    return {r.name: str(r.id) for r in rows}


# ── 端点 1a：章纲 → 分场（生成 + 持久化）────────────────────────

@router.post("/scene-plan-save")
async def scene_plan_save(
    project_id: str,
    req: ScenePlanSaveRequest,
    db: Session = Depends(get_db),
):
    """
    章纲 → 分场（三层调度第一层）。

    1. 从 outline_node 读取章节摘要/冲突/钩子，从 DB 读人物列表；
    2. 调用 ``svc.scene_plan()`` 一次性生成结构化分场计划；
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
    char_state_rows = db.query(
        Character.name,
        Character.current_realm,
        Character.current_status,
        Character.current_location,
    ).filter(Character.project_id == project_id).limit(12).all()
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
    chapter_number = node.sort_order or 0
    ingredients = await compute_chapter_ingredients(
        db=db,
        project_id=project_id,
        outline_node_id=str(req.outline_node_id),
        chapter_number=chapter_number,
    )
    constraints_block = build_constraints_prompt_block(ingredients)

    # 补充：人物关系 + 本卷情绪/反派弧 + 核心谜题约束
    plan_ctx = assemble_for_scene_plan(db, project_id, node, project)
    extra_constraints = plan_ctx.get("extra_constraints", "")
    if extra_constraints:
        constraints_block = (constraints_block or "") + "\n\n" + extra_constraints

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

        on_stage_ids: list[str] = []
        for name in sc.get("characters_on_stage", []):
            uid = char_map.get(name)
            if uid:
                on_stage_ids.append(str(uid))

        ai_loc_name: str | None = sc.get("location_name") or None
        resolved_loc_id = _resolve_location_id(ai_loc_name)

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
                        "storyline_id": str(m.storyline_id),
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
        "ingredients_summary": {
            "debt_count": len(ingredients.debt_flags),
            "must_advance_count": sum(1 for m in ingredients.storyline_moves if m.must_advance),
            "foreshadow_ops_count": len(ingredients.foreshadow_ops),
        },
    }


# ── 端点 1b：章纲 → 分场（仅返回，不持久化）─────────────────────

@router.post("/scene-plan", response_model=ScenePlanResponse)
async def scene_plan_endpoint(
    project_id: str,
    req: ScenePlanRequest,
    db: Session = Depends(get_db),
):
    """
    章纲 → 分场（Scene Plan），仅返回计划，不写入数据库。

    输出：结构化 4-8 场计划（POV、目标、冲突、转折、钩子、字数预算等）。
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
