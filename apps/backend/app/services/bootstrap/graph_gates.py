"""
Bootstrap LangGraph — Step 2 / 5 / 9 人工闸门节点。

在对应生成步骤完成后暂停，推送 gate_pending；用户 resume（approve / regenerate）后继续。
"""
from __future__ import annotations

from langgraph.types import interrupt

from app.models import Character, OutlineNode, PowerSystem, Project
from app.services.bootstrap.gate_regenerate import (
    regenerate_characters,
    regenerate_power_systems,
    regenerate_volumes,
)
from app.services.bootstrap.graph import (
    BootstrapState,
    _make_svc,
    _persist,
    _resolve_config,
    emit,
)


async def node_gate_power_systems(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 2 后闸门：确认或重生成境界体系。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    if not project:
        emit(run_id, "error", db, step="power_systems", message="项目不存在，闸门中止")
        return {"ctx": ctx, "errors": [{"step": "gate_power_systems", "reason": "no_project"}]}

    while True:
        cnt = (
            db.query(PowerSystem)
            .filter(PowerSystem.project_id == state.get("project_id"))
            .count()
        )
        emit(
            run_id,
            "gate_pending",
            db,
            persist_status="awaiting_gate",
            step="power_systems",
            message="请确认境界体系后继续；若不满意可「重新生成」本步（会覆盖当前结果）。",
            gate_preview={"power_systems_count": cnt},
        )
        _persist(db, run_id, {}, gate_data={"kind": "power_systems", "count": cnt})
        cmd = interrupt({"step": "power_systems", "kind": "power_systems_gate", "count": cnt})
        if not isinstance(cmd, dict):
            cmd = {}
        action = (cmd.get("action") or "approve").strip().lower()
        if action == "regenerate":
            emit(run_id, "step_start", db, step="power_systems", label="按你的要求重新生成境界体系…")
            n = await regenerate_power_systems(svc, project, ctx)
            emit(
                run_id,
                "step_done",
                db,
                step="power_systems",
                count=n,
                preview=f"已重新生成 {n} 套",
            )
            continue
        emit(run_id, "gate_passed", db, persist_status="running", step="power_systems")
        break
    return {"ctx": ctx}


async def node_gate_characters(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 5 后闸门：确认或重生成人物库。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    pid = state.get("project_id")
    if not project:
        emit(run_id, "error", db, step="characters", message="项目不存在，闸门中止")
        return {"ctx": ctx, "errors": [{"step": "gate_characters", "reason": "no_project"}]}

    while True:
        cnt = db.query(Character).filter(Character.project_id == pid).count()
        emit(
            run_id,
            "gate_pending",
            db,
            persist_status="awaiting_gate",
            step="characters",
            message="请确认核心人物卡后继续；「重新生成」将删除本步已写入的人物与关系后重跑。",
            gate_preview={"characters_count": cnt},
        )
        _persist(db, run_id, {}, gate_data={"kind": "characters", "count": cnt})
        cmd = interrupt({"step": "characters", "kind": "characters_gate", "count": cnt})
        if not isinstance(cmd, dict):
            cmd = {}
        action = (cmd.get("action") or "approve").strip().lower()
        if action == "regenerate":
            emit(run_id, "step_start", db, step="characters", label="按你的要求重新生成人物库…")
            n = await regenerate_characters(svc, project, ctx)
            preview = "、".join(c.name for c in db.query(Character).filter(Character.project_id == pid).limit(3).all())
            emit(run_id, "step_done", db, step="characters", count=n, preview=preview or "（已重跑）")
            continue
        emit(run_id, "gate_passed", db, persist_status="running", step="characters")
        break
    chars = db.query(Character).filter(Character.project_id == pid).all()
    ctx["_char_ids"] = [str(c.id) for c in chars]
    ctx.setdefault("protagonist", "主角")
    return {"ctx": ctx}


async def node_gate_volumes(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 9 后闸门：确认或重生成卷骨架。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    pid = state.get("project_id")
    if not project:
        emit(run_id, "error", db, step="volumes", message="项目不存在，闸门中止")
        return {"ctx": ctx, "errors": [{"step": "gate_volumes", "reason": "no_project"}]}

    while True:
        cnt = (
            db.query(OutlineNode)
            .filter(OutlineNode.project_id == pid, OutlineNode.node_type == "volume")
            .count()
        )
        emit(
            run_id,
            "gate_pending",
            db,
            persist_status="awaiting_gate",
            step="volumes",
            message="请确认卷级骨架后继续；「重新生成」将删除已写入的卷节点后重跑。",
            gate_preview={"volumes_count": cnt},
        )
        _persist(db, run_id, {}, gate_data={"kind": "volumes", "count": cnt})
        cmd = interrupt({"step": "volumes", "kind": "volumes_gate", "count": cnt})
        if not isinstance(cmd, dict):
            cmd = {}
        action = (cmd.get("action") or "approve").strip().lower()
        if action == "regenerate":
            emit(run_id, "step_start", db, step="volumes", label="按你的要求重新规划卷级结构…")
            n = await regenerate_volumes(svc, project, ctx)
            emit(
                run_id,
                "step_done",
                db,
                step="volumes",
                count=n,
                preview=f"共{n}卷" if n else "（已重跑）",
            )
            continue
        emit(run_id, "gate_passed", db, persist_status="running", step="volumes")
        break
    vols = (
        db.query(OutlineNode)
        .filter(OutlineNode.project_id == pid, OutlineNode.node_type == "volume")
        .order_by(OutlineNode.sort_order.asc())
        .all()
    )
    ctx["_volume_ids"] = [str(v.id) for v in vols]
    return {"ctx": ctx}
