"""
Bootstrap LangGraph 节点实现 — 需要自定义 ctx 操作的复杂节点。

节点职责：emit step_start → 调用对应 step 函数 → emit step_done → 返回 state patch。
简单节点（power_systems / factions / storylines / settings / memory / opening_contract）
直接在 graph.py 中通过 _run_step 一行搞定；本文件只放需要特殊处理的节点。

代码红线：本文件 < 300 行。
"""
from __future__ import annotations

import asyncio
import logging

from app.services.bootstrap.graph import BootstrapState, _make_svc, emit, _resolve_config

logger = logging.getLogger(__name__)


async def node_characters(state: BootstrapState, config: dict | None = None) -> dict:
    """
    Step 5：生成人物库。将 chars 列表存入 ctx["_chars"] 供 node_relations 使用。

    @returns state patch: ctx（含 _chars）、completed_steps
    """
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="characters", label="生成人物库...")
    ctx = dict(state.get("ctx") or {})
    from app.models import Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    try:
        chars = await asyncio.wait_for(svc._gen_characters(project, ctx), timeout=300.0)
    except asyncio.TimeoutError:
        emit(run_id, "error", db, step="characters", message="人物库生成超时，已跳过")
        return {"ctx": ctx, "completed_steps": ["characters"],
                "errors": [{"step": "characters", "reason": "timeout"}]}
    except Exception as exc:
        emit(run_id, "error", db, step="characters", message=f"人物库生成失败：{exc}")
        return {"ctx": ctx, "completed_steps": ["characters"],
                "errors": [{"step": "characters", "reason": str(exc)}]}
    ctx.setdefault("protagonist", "主角")
    # 仅保存可序列化的主键列表，避免将 ORM 对象写入 LangGraph checkpoint。
    ctx["_char_ids"] = [str(c.id) for c in chars]
    preview = "、".join(c.name for c in chars[:3]) if chars else "（跳过）"
    emit(run_id, "step_done", db, step="characters", count=len(chars), preview=preview)
    return {"ctx": ctx, "completed_steps": ["characters"]}


async def node_skills_items(state: BootstrapState, config: dict | None = None) -> dict:
    """
    Step 6 + 7 并行：功法技能 + 关键道具（asyncio.gather）。

    @returns state patch: ctx、completed_steps（同时包含 skills 和 items）
    """
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="skills", label="生成核心功法技能...")
    emit(run_id, "step_start", db, step="items",  label="生成关键道具法宝...")
    ctx = dict(state.get("ctx") or {})
    from app.models import Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                svc._gen_key_skills(project, ctx),
                svc._gen_key_items(project, ctx),
                return_exceptions=True,
            ),
            timeout=240.0,
        )
    except asyncio.TimeoutError:
        for s in ("skills", "items"):
            emit(run_id, "error", db, step=s, message="并行生成超时，已跳过")
        return {"ctx": ctx, "completed_steps": ["skills", "items"],
                "errors": [{"step": "skills_items", "reason": "timeout"}]}
    skills = results[0] if not isinstance(results[0], BaseException) else []
    items  = results[1] if not isinstance(results[1], BaseException) else []
    for step, res in (("skills", results[0]), ("items", results[1])):
        if isinstance(res, BaseException):
            emit(run_id, "error", db, step=step, message=f"生成失败：{res}")
    emit(run_id, "step_done", db, step="skills", count=len(skills))
    emit(run_id, "step_done", db, step="items",  count=len(items))
    return {"ctx": ctx, "completed_steps": ["skills", "items"]}


async def node_volumes(state: BootstrapState, config: dict | None = None) -> dict:
    """
    Step 9：卷级大纲。将 volumes 列表存入 ctx["_volumes"] 供 node_vol1_chapters 使用。

    @returns state patch: ctx（含 _volumes）、completed_steps
    """
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="volumes", label="规划卷级结构...")
    ctx = dict(state.get("ctx") or {})
    from app.models import Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    try:
        nodes = await asyncio.wait_for(svc._gen_volumes(project, ctx), timeout=300.0)
    except (asyncio.TimeoutError, Exception) as exc:
        reason = "timeout" if isinstance(exc, asyncio.TimeoutError) else str(exc)
        emit(run_id, "error", db, step="volumes", message=f"卷级结构生成失败：{reason}")
        return {"ctx": ctx, "completed_steps": ["volumes"],
                "errors": [{"step": "volumes", "reason": reason}]}
    # 仅保存可序列化的主键列表，避免将 ORM 对象写入 LangGraph checkpoint。
    ctx["_volume_ids"] = [str(n.id) for n in nodes]
    emit(run_id, "step_done", db, step="volumes", count=len(nodes),
         preview=f"共{len(nodes)}卷" if nodes else "（跳过）")
    return {"ctx": ctx, "completed_steps": ["volumes"]}


async def node_relations(state: BootstrapState, config: dict | None = None) -> dict:
    """
    Step 11：人物关系。从 ctx["_chars"] 取人物列表；若已被 pop 则回退到 DB 查询。

    @returns state patch: ctx（已移除 _chars）、completed_steps
    """
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="relations", label="建立人物关系...")
    ctx = dict(state.get("ctx") or {})
    from app.models import Project, Character
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    char_ids = ctx.pop("_char_ids", None) or []
    if char_ids:
        chars = db.query(Character).filter(Character.id.in_(char_ids)).all()
    else:
        chars = db.query(Character).filter(
            Character.project_id == state.get("project_id")
        ).all()
    try:
        rels = await asyncio.wait_for(svc._gen_relations(project, chars, ctx), timeout=240.0)
    except (asyncio.TimeoutError, Exception) as exc:
        reason = "timeout" if isinstance(exc, asyncio.TimeoutError) else str(exc)
        emit(run_id, "error", db, step="relations", message=f"人物关系生成失败：{reason}")
        return {"ctx": ctx, "completed_steps": ["relations"],
                "errors": [{"step": "relations", "reason": reason}]}
    emit(run_id, "step_done", db, step="relations", count=len(rels))
    return {"ctx": ctx, "completed_steps": ["relations"]}


async def node_vol1_chapters(state: BootstrapState, config: dict | None = None) -> dict:
    """
    Step 12.5：第一卷章级大纲。从 ctx["_volumes"] 取卷列表；结果存入 ctx["_vol1_plans"]。

    @returns state patch: ctx（含 _vol1_plans）、completed_steps
    """
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="vol1_chapters", label="生成第一卷章级大纲...")
    ctx = dict(state.get("ctx") or {})
    from app.models import Project, OutlineNode
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    volume_ids = ctx.get("_volume_ids") or []
    volumes = (
        db.query(OutlineNode)
        .filter(OutlineNode.id.in_(volume_ids), OutlineNode.node_type == "volume")
        .order_by(OutlineNode.sort_order.asc())
        .all()
        if volume_ids else []
    )
    try:
        plans = await asyncio.wait_for(
            svc._gen_vol1_chapter_plans(project, volumes, ctx), timeout=360.0
        )
    except (asyncio.TimeoutError, Exception) as exc:
        reason = "timeout" if isinstance(exc, asyncio.TimeoutError) else str(exc)
        emit(run_id, "error", db, step="vol1_chapters", message=f"章级大纲生成失败：{reason}")
        return {"ctx": ctx, "completed_steps": ["vol1_chapters"],
                "errors": [{"step": "vol1_chapters", "reason": reason}]}
    # 仅保存可序列化的主键列表，供下一步场景蓝图使用。
    ctx["_vol1_plan_ids"] = [str(p.id) for p in plans]
    emit(run_id, "step_done", db, step="vol1_chapters", count=len(plans),
         preview=f"第一卷共{len(plans)}章蓝图" if plans else "（跳过）")
    return {"ctx": ctx, "completed_steps": ["vol1_chapters"]}


async def node_ch1_scenes(state: BootstrapState, config: dict | None = None) -> dict:
    """
    Step 13：第1章场景蓝图。从 ctx["_vol1_plans"] 取章纲列表。

    @returns state patch: ctx、completed_steps
    """
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="ch1_scenes", label="生成第1章场景蓝图...")
    ctx = dict(state.get("ctx") or {})
    from app.models import Project, OutlineNode
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    vol1_plan_ids = ctx.get("_vol1_plan_ids") or []
    vol1_plans = (
        db.query(OutlineNode)
        .filter(OutlineNode.id.in_(vol1_plan_ids), OutlineNode.node_type == "chapter_plan")
        .order_by(OutlineNode.sort_order.asc())
        .all()
        if vol1_plan_ids else []
    )
    try:
        scenes = await asyncio.wait_for(
            svc._gen_ch1_scenes(project, vol1_plans, ctx), timeout=240.0
        )
    except (asyncio.TimeoutError, Exception) as exc:
        reason = "timeout" if isinstance(exc, asyncio.TimeoutError) else str(exc)
        emit(run_id, "error", db, step="ch1_scenes", message=f"场景蓝图生成失败：{reason}")
        return {"ctx": ctx, "completed_steps": ["ch1_scenes"],
                "errors": [{"step": "ch1_scenes", "reason": reason}]}
    emit(run_id, "step_done", db, step="ch1_scenes", count=len(scenes),
         preview=f"第1章共{len(scenes)}场" if scenes else "（跳过）")
    return {"ctx": ctx, "completed_steps": ["ch1_scenes"]}


async def node_consistency(state: BootstrapState, config: dict | None = None) -> dict:
    """
    Step 14：全局一致性扫描（最后一步）。完成后发送 complete 事件并更新 status=done。

    @returns state patch: ctx、completed_steps
    """
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="consistency", label="全局一致性扫描...")
    ctx = dict(state.get("ctx") or {})
    from app.models import Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    try:
        issues = await asyncio.wait_for(svc._gen_consistency_scan(project, ctx), timeout=240.0)
    except (asyncio.TimeoutError, Exception) as exc:
        issues = []
        emit(run_id, "error", db, step="consistency", message=f"一致性扫描失败：{exc}")
    emit(run_id, "step_done", db, step="consistency", count=len(issues),
         preview=f"发现{len(issues)}处需确认项" if issues else "无明显矛盾")
    emit(run_id, "complete", db, persist_status="done", project_id=state.get("project_id"))
    return {"ctx": ctx, "completed_steps": ["consistency"]}
