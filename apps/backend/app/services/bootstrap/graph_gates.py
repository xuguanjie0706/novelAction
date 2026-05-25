"""
Bootstrap LangGraph — Step 2 / 5 / 9 人工闸门节点。

在对应生成步骤完成后暂停，推送 gate_pending；用户 resume（approve / regenerate）后继续。
"""
from __future__ import annotations

from langgraph.types import interrupt
from sqlalchemy import case
from sqlalchemy.orm import aliased

from app.models import Character, CharacterRelationship, OutlineNode, PowerSystem, Project
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


def _characters_gate_preview(db, pid) -> dict:
    """
    人物闸门审阅用摘要：角色条目前 40 条 + 关系总数 + 关系样本（JOIN 人名），写入 gate_preview / gate_data。

    Returns:
        可直接展开进 ``emit(..., gate_preview=...)`` 的 dict（含 ``characters_count``）。
    """
    total = db.query(Character).filter(Character.project_id == pid).count()
    role_rank = case(
        (Character.role == "protagonist", 0),
        (Character.role == "antagonist", 1),
        (Character.role == "supporting", 2),
        else_=3,
    )
    chars = (
        db.query(Character)
        .filter(Character.project_id == pid)
        .order_by(role_rank, Character.name)
        .limit(40)
        .all()
    )
    characters_preview = [
        {
            "name": c.name,
            "role": (c.role or "").strip(),
            "character_tier": (c.character_tier or "").strip(),
            "faction": (c.faction or "").strip() or None,
            "current_realm": (c.current_realm or "").strip() or None,
            "gender": (c.gender or "").strip() or None,
        }
        for c in chars
    ]
    rel_cnt = (
        db.query(CharacterRelationship)
        .filter(CharacterRelationship.project_id == pid)
        .count()
    )
    Fa = aliased(Character)
    Ta = aliased(Character)
    rel_rows = (
        db.query(Fa.name, Ta.name, CharacterRelationship.relation_type)
        .select_from(CharacterRelationship)
        .join(Fa, CharacterRelationship.from_character_id == Fa.id)
        .join(Ta, CharacterRelationship.to_character_id == Ta.id)
        .filter(CharacterRelationship.project_id == pid)
        .order_by(CharacterRelationship.relation_type, Fa.name, Ta.name)
        .limit(15)
        .all()
    )
    relations_sample = [
        {
            "from": a,
            "to": b,
            "relation_type": (t or "").strip() or "关联",
        }
        for a, b, t in rel_rows
    ]
    return {
        "count": total,
        "characters_count": total,
        "characters_preview": characters_preview,
        "characters_preview_truncated": total > len(characters_preview),
        "relations_count": rel_cnt,
        "relations_sample": relations_sample,
    }


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
        pss = (
            db.query(PowerSystem)
            .filter(PowerSystem.project_id == state.get("project_id"))
            .order_by(PowerSystem.sort_order)
            .all()
        )
        from app.services.bootstrap.power_registry import axis_role_of, merge_power_into_ctx

        merge_power_into_ctx(ctx, pss, project=project)
        axis_summary = [
            {"name": ps.name, "axis": axis_role_of(ps), "levels": len(ps.levels or [])}
            for ps in pss
        ]
        emit(
            run_id,
            "gate_pending",
            db,
            persist_status="awaiting_gate",
            step="power_systems",
            message="请确认境界体系后继续；若不满意可「重新生成」本步（会覆盖当前结果）。",
            gate_preview={
                "power_systems_count": cnt,
                "power_axes": axis_summary,
                "primary_ladder": ctx.get("power_level_names") or [],
            },
        )
        _persist(db, run_id, {}, gate_data={"kind": "power_systems", "count": cnt, "current_gate": "gate_power_systems"})
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
        preview = _characters_gate_preview(db, pid)
        emit(
            run_id,
            "gate_pending",
            db,
            persist_status="awaiting_gate",
            step="characters",
            message="请确认核心人物卡后继续；「重新生成」将删除本步已写入的人物与关系后重跑。",
            gate_preview=preview,
        )
        _persist(db, run_id, {}, gate_data={"kind": "characters", "current_gate": "gate_characters", **preview})
        cmd = interrupt({"step": "characters", "kind": "characters_gate", "count": preview["characters_count"]})
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

    from app.services.bootstrap.volume_entity_registry import build_volumes_gate_preview

    while True:
        preview = build_volumes_gate_preview(db, pid, ctx)
        gate_msg = "请确认卷级骨架后继续；「重新生成」将删除已写入的卷节点后重跑。"
        if preview.get("has_realm_warnings"):
            gate_msg = (
                "⚠️ 检测到卷级 BOSS 境界曲线异常（后期卷不高于前期卷），"
                "建议点「重新生成此步」修正后再继续。"
            )
        emit(
            run_id,
            "gate_pending",
            db,
            persist_status="awaiting_gate",
            step="volumes",
            message=gate_msg,
            gate_preview=preview,
        )
        _persist(
            db,
            run_id,
            {},
            gate_data={"kind": "volumes", "current_gate": "gate_volumes", **preview},
        )
        cmd = interrupt({
            "step": "volumes",
            "kind": "volumes_gate",
            "count": preview.get("volumes_count", 0),
        })
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
