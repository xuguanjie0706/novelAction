"""
graph_fanfic.py — 同人·番茄 Bootstrap LangGraph

拓扑：
  START → fanfic_positioning → gate → project
  → canon_pack → deviation_contract → entry_hook
  → golden_finger → face_slap_map → canon_power
  → canon_characters → volumes → rhythm_map → canon_audit → END
"""
from __future__ import annotations

import asyncio
import logging

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

from app.database import SessionLocal
from app.models import Project
from app.models.bootstrap_run import BootstrapRun
from app.services.bootstrap.graph_ctx import sanitize_bootstrap_ctx
from app.services.bootstrap.graph import (
    BootstrapState,
    _make_svc,
    _persist,
    _resolve_config,
    _state_run_id,
    emit,
    _push,
    _handle_run_error,
    get_fanfic_graph,
)
from app.services.bootstrap.steps.project import gen_project

logger = logging.getLogger(__name__)


def _fanfic_step_result_ok(result) -> tuple[bool, int]:
    """判断步骤产物是否有效；返回 (是否成功, 用于 step_done 的 count)。"""
    if isinstance(result, list):
        return len(result) > 0, len(result)
    if isinstance(result, dict):
        return bool(result), (1 if result else 0)
    return bool(result), (1 if result else 0)


async def _fanfic_step(
    state: BootstrapState,
    config: dict | None,
    step: str,
    label: str,
    fn,
    *,
    needs_project: bool = True,
) -> dict:
    """emit start → fn → emit done；失败则 interrupt 等待用户 retry_step（与通用 _run_step 一致）。"""
    from app.services.bootstrap.step_failure import pause_for_step_retry, user_wants_step_retry
    from app.services.llm_errors import format_llm_error_message

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    project = None
    if needs_project:
        project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    from app.services.bootstrap.json_once import BootstrapStepError

    while True:
        emit(run_id, "step_start", db, step=step, label=label)
        try:
            if needs_project:
                result = await asyncio.wait_for(fn(svc, project, ctx), timeout=300.0)
            else:
                result = await asyncio.wait_for(fn(svc, ctx), timeout=300.0)
        except BootstrapStepError as exc:
            emit(run_id, "error", db, step=step, message=str(exc))
            raise
        except asyncio.TimeoutError:
            msg = f"{step} 超时（5 分钟），请重试或检查模型线路"
        except Exception as exc:
            msg = f"{step} 失败：{format_llm_error_message(exc)}"
        else:
            ok, count = _fanfic_step_result_ok(result)
            if ok:
                emit(run_id, "step_done", db, step=step, count=count)
                return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": [step]}
            msg = f"{step} 生成结果为空，请重试或更换模型线路"

        user = await pause_for_step_retry(state, config, step=step, message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": sanitize_bootstrap_ctx(ctx), "errors": [{"step": step, "reason": msg}]}


async def node_fanfic_positioning(state: BootstrapState, config: dict | None = None) -> dict:
    from app.services.bootstrap.steps.fanfic.fanfic_positioning import gen_fanfic_positioning

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="positioning", label="召开同人·番茄立项会议...")
    ctx = dict(state.get("ctx") or {})
    ctx.update({
        "logline": state["logline"],
        "premise": state["premise"],
        "target_words": state["target_words"],
    })
    pos = await gen_fanfic_positioning(svc, ctx)
    ctx["fanfic_positioning"] = pos
    ctx["positioning"] = _to_generic_positioning(pos, ctx.get("fanfic_meta") or {})

    emit(run_id, "step_done", db, step="positioning", count=1,
         preview=pos.get("fanfic_trope_label", "")[:30])
    emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
         step="positioning", positioning=pos,
         message="请确认同人立项（类型/爽感/雷区）后继续生成")
    _persist(db, run_id, {}, gate_data={
        "kind": "positioning",
        "positioning": pos,
        "logline": state["logline"],
        "premise": state.get("premise") or "",
        "target_words": state.get("target_words"),
        "fanfic_meta": ctx.get("fanfic_meta"),
    })
    return {"positioning": pos, "ctx": ctx, "completed_steps": ["positioning"]}


async def node_fanfic_gate(state: BootstrapState, config: dict | None = None) -> dict:
    from app.services.bootstrap.steps.fanfic.fanfic_positioning import gen_fanfic_positioning

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    positioning = dict(state.get("positioning") or {})
    ctx = dict(state.get("ctx") or {})

    while True:
        user_input = interrupt({"type": "positioning_gate", "step": "positioning", "positioning": positioning})
        if not isinstance(user_input, dict):
            user_input = {}
        action = (user_input.get("action") or "approve").strip().lower()
        if action == "regenerate":
            ctx.update({"logline": state["logline"], "premise": state["premise"],
                        "target_words": state["target_words"]})
            positioning = await gen_fanfic_positioning(svc, ctx)
            ctx["fanfic_positioning"] = positioning
            ctx["positioning"] = _to_generic_positioning(positioning, ctx.get("fanfic_meta") or {})
            emit(run_id, "step_done", db, step="positioning", count=1,
                 preview=positioning.get("fanfic_trope_label", "")[:30])
            emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
                 step="positioning", positioning=positioning,
                 message="请再次确认同人立项后继续")
            _persist(db, run_id, {}, gate_data={
                "kind": "positioning", "positioning": positioning,
                "logline": state["logline"], "fanfic_meta": ctx.get("fanfic_meta"),
            })
            continue
        updated = user_input.get("positioning", positioning)
        if not isinstance(updated, dict):
            updated = positioning
        ctx["fanfic_positioning"] = updated
        ctx["positioning"] = _to_generic_positioning(updated, ctx.get("fanfic_meta") or {})
        emit(run_id, "gate_passed", db, persist_status="running", step="positioning", positioning=updated)
        return {"positioning": updated, "ctx": ctx}


async def node_project(state: BootstrapState, config: dict | None = None) -> dict:
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="project", label="生成同人项目基础信息...")
    ctx = dict(state.get("ctx") or {})
    project, ctx = await gen_project(svc, ctx)
    extra = dict(project.extra or {})
    extra["bootstrap_mode"] = "fanfic"
    if ctx.get("fanfic_meta"):
        extra["fanfic_meta"] = ctx["fanfic_meta"]
    if ctx.get("fanfic_positioning"):
        extra["fanfic_positioning"] = ctx["fanfic_positioning"]
    project.extra = extra
    svc.db.commit()
    emit(run_id, "step_done", db, step="project", count=1, preview=f"《{project.title}》同人")
    _persist(db, run_id, {}, project_id=str(project.id))
    return {"project_id": str(project.id), "ctx": ctx, "completed_steps": ["project"]}


async def node_canon_pack(s, c=None):
    from app.services.bootstrap.steps.fanfic.canon_pack import gen_canon_pack
    return await _fanfic_step(s, c, "canon_pack", "结构化原著设定...", gen_canon_pack)


async def node_deviation(s, c=None):
    from app.services.bootstrap.steps.fanfic.deviation_contract import gen_deviation_contract
    return await _fanfic_step(s, c, "deviation_contract", "订立魔改边界...", gen_deviation_contract)


async def node_entry_hook(s, c=None):
    from app.services.bootstrap.steps.fanfic.entry_hook import gen_entry_hook
    return await _fanfic_step(s, c, "entry_hook", "设计穿书/重生/AU 切入点...", gen_entry_hook)


async def node_golden_finger(s, c=None):
    from app.services.bootstrap.steps.fanfic.golden_finger_fanfic import gen_golden_finger_fanfic
    return await _fanfic_step(s, c, "golden_finger", "设计同人金手指/信息差...", gen_golden_finger_fanfic)


async def node_face_slap(s, c=None):
    from app.services.bootstrap.steps.fanfic.face_slap_fanfic import gen_face_slap_fanfic
    return await _fanfic_step(s, c, "face_slap_map", "规划打脸地图...", gen_face_slap_fanfic)


async def node_canon_power(s, c=None):
    from app.services.bootstrap.steps.fanfic.canon_power import gen_canon_power
    return await _fanfic_step(s, c, "canon_power", "提炼原著权力阶梯...", gen_canon_power)


async def node_canon_characters(s, c=None):
    from app.services.bootstrap.steps.fanfic.canon_characters import gen_canon_characters
    return await _fanfic_step(s, c, "canon_characters", "原著人物建档...", gen_canon_characters)


async def node_volumes(s, c=None):
    from app.services.bootstrap.steps.volumes import gen_volumes
    return await _fanfic_step(s, c, "volumes", "规划全书卷级骨架...", gen_volumes)


async def node_rhythm(s, c=None):
    from app.services.bootstrap.steps.fanfic.rhythm_fanfic import gen_rhythm_fanfic
    return await _fanfic_step(s, c, "rhythm_map", "生成爽点节奏图...", gen_rhythm_fanfic)


async def node_audit(s, c=None):
    from app.services.bootstrap.steps.fanfic.canon_audit import gen_canon_audit

    patch = await _fanfic_step(s, c, "canon_audit", "原著贴合 + 爽感双校验...", gen_canon_audit)
    config = _resolve_config(c)
    db = config["configurable"]["db"]
    run_id = _state_run_id(s, config)
    project_id = s.get("project_id")
    if project_id:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            merged_ctx = dict(s.get("ctx") or {})
            merged_ctx.update(patch.get("ctx") or {})
            from app.services.bootstrap.fanfic_normalize import converge_fanfic_project
            converge_fanfic_project(db, project, merged_ctx)
    emit(run_id, "complete", db, persist_status="done", project_id=s.get("project_id"))
    return patch


def _build_fanfic_graph(checkpointer):
    g = StateGraph(BootstrapState)
    for name, fn in [
        ("fanfic_positioning", node_fanfic_positioning),
        ("gate", node_fanfic_gate),
        ("project", node_project),
        ("canon_pack", node_canon_pack),
        ("deviation_contract", node_deviation),
        ("entry_hook", node_entry_hook),
        ("golden_finger", node_golden_finger),
        ("face_slap_map", node_face_slap),
        ("canon_power", node_canon_power),
        ("canon_characters", node_canon_characters),
        ("volumes", node_volumes),
        ("rhythm_map", node_rhythm),
        ("canon_audit", node_audit),
    ]:
        g.add_node(name, fn)
    chain = [
        START, "fanfic_positioning", "gate", "project",
        "canon_pack", "deviation_contract", "entry_hook",
        "golden_finger", "face_slap_map", "canon_power",
        "canon_characters", "volumes", "rhythm_map", "canon_audit", END,
    ]
    for a, b in zip(chain, chain[1:]):
        g.add_edge(a, b)
    return g.compile(checkpointer=checkpointer, interrupt_before=["gate"])


async def run_bootstrap_fanfic(
    run_id: str, *, logline: str, premise: str, target_words: int,
    model_profile: str, llm_provider_id, user_id,
    writing_style: str = "plain",
    fanfic_meta: dict | None = None,
) -> None:
    fanfic_graph = get_fanfic_graph()
    db = SessionLocal()
    try:
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if run:
            run.status = "running"
            db.commit()
        _ws = str(writing_style or "").strip().lower()
        if _ws not in ("plain", "standard", "dense"):
            _ws = "plain"
        initial: BootstrapState = {
            "run_id": run_id, "logline": logline, "premise": premise,
            "target_words": target_words, "positioning": {}, "project_id": None,
            "ctx": {
                "writing_style": _ws,
                "fanfic_meta": fanfic_meta or {},
            },
            "completed_steps": [], "errors": [],
        }
        config = {"configurable": {
            "thread_id": run_id, "db": db,
            "model_profile": model_profile,
            "llm_provider_id": llm_provider_id,
            "user_id": user_id,
        }}
        await fanfic_graph.ainvoke(initial, config=config)
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if not run or run.status not in ("awaiting_gate", "awaiting_retry"):
            _push(run_id, {"event": "__stream_end__"})
        else:
            from app.services.bootstrap.gate_auto import schedule_auto_resume_for_run
            schedule_auto_resume_for_run(run_id)
    except asyncio.CancelledError:
        emit(run_id, "cancelled", db, persist_status="cancelled", message="用户已取消生成")
        _push(run_id, {"event": "__stream_end__"})
        raise
    except Exception as exc:
        logger.exception("Fanfic bootstrap run %s failed", run_id)
        _handle_run_error(db, run_id, exc)
        _push(run_id, {"event": "__stream_end__"})
    finally:
        db.close()


async def resume_bootstrap_fanfic(
    run_id: str, resume_payload: dict, *,
    model_profile: str, llm_provider_id, user_id,
) -> None:
    from app.services.bootstrap.gate_auto import resume_lock

    async with resume_lock(run_id):
        await _resume_bootstrap_fanfic_impl(
            run_id, resume_payload,
            model_profile=model_profile,
            llm_provider_id=llm_provider_id,
            user_id=user_id,
        )


async def _resume_bootstrap_fanfic_impl(
    run_id: str, resume_payload: dict, *,
    model_profile: str, llm_provider_id, user_id,
) -> None:
    fanfic_graph = get_fanfic_graph()
    db = SessionLocal()
    try:
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if run:
            run.status = "running"
            db.commit()
        config = {"configurable": {
            "thread_id": run_id, "db": db,
            "model_profile": model_profile,
            "llm_provider_id": llm_provider_id,
            "user_id": user_id,
        }}
        await fanfic_graph.ainvoke(Command(resume=dict(resume_payload)), config=config)
    except asyncio.CancelledError:
        emit(run_id, "cancelled", db, persist_status="cancelled", message="用户已取消生成")
        raise
    except Exception as exc:
        logger.exception("Fanfic bootstrap resume %s failed", run_id)
        _handle_run_error(db, run_id, exc)
    finally:
        try:
            run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
            if run and run.status in ("done", "failed", "cancelled"):
                _push(run_id, {"event": "__stream_end__"})
            elif run and run.status == "awaiting_gate":
                from app.services.bootstrap.gate_auto import schedule_auto_resume_for_run
                schedule_auto_resume_for_run(run_id)
            # awaiting_retry：保持 SSE 订阅，等待用户 retry_step
        except Exception:
            pass
        db.close()


def _to_generic_positioning(fanfic_pos: dict, meta: dict) -> dict:
    title = fanfic_pos.get("source_work_title") or meta.get("source_work_title", "")
    trope = fanfic_pos.get("fanfic_trope_label", "")
    return {
        "bootstrap_mode": "fanfic",
        "source_work_title": title,
        "target_audience": f"番茄同人·{trope}读者",
        "tropes": fanfic_pos.get("platform_tags", []),
        "reference_works": [title] if title else [],
        "selling_point": fanfic_pos.get("algo_hook", ""),
        "face_slap_pattern": "每3章一小打，每10章一大打",
        "emotional_arc": "同人爽文：原著味+新爽点",
        "pace_type": "fast",
        "taboo_lines": list(fanfic_pos.get("ooc_taboos") or []) or ["无"],
    }
