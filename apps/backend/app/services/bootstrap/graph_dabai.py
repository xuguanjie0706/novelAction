"""graph_dabai.py — 玄幻修仙大白文线（mode=dabai）专属 LangGraph 节点。

约 4 次 LLM + 规则 lint；止于卷骨架（含地图+境界区间），章纲写作期懒展开。
红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

import asyncio
import logging

from langgraph.types import interrupt

from app.models import Project
from app.services.bootstrap.graph import (
    BootstrapState,
    _make_svc,
    _persist,
    _resolve_config,
    _state_run_id,
    emit,
)
from app.services.bootstrap.graph_ctx import sanitize_bootstrap_ctx
from app.services.bootstrap.graph_doupo import _doupo_step

logger = logging.getLogger(__name__)


async def node_dabai_positioning(state: BootstrapState, config: dict | None = None) -> dict:
    from app.services.bootstrap.steps.dabai.positioning_dabai import gen_dabai_positioning

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="positioning",
         label="召开大白文·修仙立项（对标+爽点池）...")
    ctx = dict(state.get("ctx") or {})
    ctx.update({"logline": state["logline"], "premise": state["premise"],
                "target_words": state["target_words"]})
    dp = await gen_dabai_positioning(svc, ctx)

    emit(run_id, "step_done", db, step="positioning", count=1,
         preview=f"{dp.get('subgenre', '修仙')[:12]}·{dp.get('core_satisfaction', '升级打脸')[:14]}")
    emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
         step="positioning", positioning=dp,
         message="请确认大白文修仙立项后继续")
    _persist(db, run_id, {}, gate_data={
        "kind": "positioning", "positioning": dp,
        "benchmark": ctx.get("benchmark") or {},
        "logline": state["logline"], "premise": state.get("premise") or "",
        "target_words": state.get("target_words"),
    })
    return {"positioning": dp, "ctx": ctx, "completed_steps": ["positioning"]}


async def node_dabai_gate(state: BootstrapState, config: dict | None = None) -> dict:
    from app.services.bootstrap.steps.dabai.positioning_dabai import (
        gen_dabai_positioning,
        to_generic_positioning,
    )

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    positioning = dict(state.get("positioning") or {})
    ctx = dict(state.get("ctx") or {})

    while True:
        user_input = interrupt({"type": "positioning_gate", "step": "positioning",
                                "positioning": positioning})
        if not isinstance(user_input, dict):
            user_input = {}
        action = (user_input.get("action") or "approve").strip().lower()
        if action == "regenerate":
            ctx.update({"logline": state["logline"], "premise": state["premise"],
                        "target_words": state["target_words"]})
            positioning = await gen_dabai_positioning(svc, ctx)
            emit(run_id, "step_done", db, step="positioning", count=1)
            emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
                 step="positioning", positioning=positioning,
                 message="请再次确认立项后继续")
            _persist(db, run_id, {}, gate_data={
                "kind": "positioning", "positioning": positioning,
                "benchmark": ctx.get("benchmark") or {},
                "logline": state["logline"], "premise": state.get("premise") or "",
                "target_words": state.get("target_words"),
            })
            continue
        updated = user_input.get("positioning", positioning)
        if not isinstance(updated, dict):
            updated = positioning
        ctx["dabai_positioning"] = updated
        ctx["positioning"] = to_generic_positioning(updated)
        ctx["bootstrap_mode"] = "dabai"
        emit(run_id, "gate_passed", db, persist_status="running",
             step="positioning", positioning=updated)
        return {"positioning": updated, "ctx": ctx}


async def node_golden_power_dabai(s, c=None):
    from app.services.bootstrap.steps.dabai.golden_power_dabai import gen_golden_power_dabai

    return await _doupo_step(
        s, c, "power_ladder", "金手指 + 修仙境界主轴 + 境界预算契约（合并）...",
        gen_golden_power_dabai,
    )


async def node_cast_world_dabai(s, c=None):
    from app.services.bootstrap.steps.dabai.cast_world_dabai import gen_cast_world_dabai

    return await _doupo_step(
        s, c, "factions", "势力 + 人物 + 故事线 + 卷级对立面（合并）...",
        gen_cast_world_dabai,
    )


async def node_volumes_map_dabai(state: BootstrapState, config: dict | None = None) -> dict:
    from app.services.bootstrap.steps.dabai.volumes_map_dabai import gen_volumes_map_dabai
    from app.services.bootstrap.step_failure import pause_for_step_retry, user_wants_step_retry
    from app.services.llm_errors import format_llm_error_message

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    while True:
        emit(run_id, "step_start", db, step="volumes",
             label="规划卷骨架（地图 + 境界区间）...")
        try:
            nodes = await asyncio.wait_for(
                gen_volumes_map_dabai(svc, project, ctx), timeout=300.0,
            )
        except asyncio.TimeoutError:
            msg = "卷级结构生成超时（5 分钟），请重试"
        except Exception as exc:
            msg = f"卷级结构生成失败：{format_llm_error_message(exc)}"
            logger.warning("dabai.volumes_map 失败 project=%s: %s", state.get("project_id"), exc)
        else:
            if nodes:
                ctx["_volume_ids"] = [str(n.id) for n in nodes]
                emit(run_id, "step_done", db, step="volumes", count=len(nodes),
                     preview=f"共{len(nodes)}卷（地图+境界已锁）")
                return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": ["volumes"]}
            msg = "卷级结构生成结果为空，请重试"

        user = await pause_for_step_retry(state, config, step="volumes", message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": sanitize_bootstrap_ctx(ctx), "errors": [{"step": "volumes", "reason": msg}]}


async def node_dabai_bootstrap_lint(state: BootstrapState, config: dict | None = None) -> dict:
    """大白文 Bootstrap 收尾质检；成功后 emit complete 标记 run 完成。"""
    from app.services.bootstrap.step_failure import pause_for_step_retry, user_wants_step_retry
    from app.services.bootstrap.steps.dabai.dabai_bootstrap_lint import run_dabai_bootstrap_lint
    from app.services.llm_errors import format_llm_error_message

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    while True:
        emit(run_id, "step_start", db, step="consistency",
             label="大白文 Bootstrap 规则质检（无 LLM）...")
        try:
            report = await asyncio.wait_for(
                asyncio.to_thread(run_dabai_bootstrap_lint, svc, project, ctx),
                timeout=120.0,
            )
        except asyncio.TimeoutError:
            msg = "规则质检超时，请重试"
        except Exception as exc:
            msg = f"规则质检失败：{format_llm_error_message(exc)}"
            logger.warning("dabai.bootstrap_lint 失败 project=%s: %s", state.get("project_id"), exc)
        else:
            if report:
                n = int(report.get("issue_count") or 0)
                preview = "无明显问题" if report.get("status") == "ok" else f"发现{n}项需确认"
                emit(run_id, "step_done", db, step="consistency", count=n, preview=preview)
                emit(run_id, "complete", db, persist_status="done",
                     project_id=state.get("project_id"))
                return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": ["consistency"]}
            msg = "规则质检结果为空，请重试"

        user = await pause_for_step_retry(state, config, step="consistency", message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": sanitize_bootstrap_ctx(ctx), "errors": [{"step": "consistency", "reason": msg}]}
