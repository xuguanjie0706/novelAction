"""
graph_fanqie.py — 番茄小说专属 Bootstrap LangGraph

拓扑（9阶段18步）：
  START
  → fanqie_positioning        # Phase A: 算法立项（类型选型/爽感宣言/竞品差异）
  → gate                      # 立项确认闸门（与通用流程共用 gate 节点）
  → project                   # 创建 Project 记录（复用通用 gen_project）
  → contrast_design           # Phase B: 落差工程（初始状态/触发事件）
  → golden_finger             # Phase C: 金手指工程（类型/可视化/成长路线图）
  → face_slap_map             # Phase D: 打脸地图（对象谱系/首次打脸/类型多样性）
  → power_ladder              # Phase E: 权力阶梯（最小化世界观）
  → character_functions       # Phase E: 人物功能表 + 登场序列
  → opening_5chapters         # Phase F: 开局五章工程（算法生死线）
  → rhythm_map                # Phase G: 爽点节奏图 + 剧情储量池
  → signal_audit              # Phase H: 算法双校验
  → END

复用：BootstrapState / emit / _push / subscribe / unsubscribe / _persist 来自 graph.py；
      checkpointer 与主图共用 AsyncPostgresSaver（graph.init_bootstrap_graph 内编译 fanqie_graph）。

代码红线：本文件 < 300 行。
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
    subscribe,
    unsubscribe,
    _push,
    _handle_run_error,
    get_fanqie_graph,
)
from app.services.bootstrap.steps.project import gen_project

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────
# 通用薄步骤执行器（Fanqie 版）
# ──────────────────────────────────────────────────────


async def _fanqie_step(
    state: BootstrapState,
    config: dict | None,
    step: str,
    label: str,
    fn,
    *,
    needs_project: bool = True,
) -> dict:
    """emit start → fn(svc, project, ctx) → emit done；超时/异常跳过不中断图。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step=step, label=label)
    ctx = dict(state.get("ctx") or {})
    project = None
    if needs_project:
        project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    try:
        if needs_project:
            result = await asyncio.wait_for(fn(svc, project, ctx), timeout=300.0)
        else:
            result = await asyncio.wait_for(fn(svc, ctx), timeout=300.0)
    except asyncio.TimeoutError:
        emit(run_id, "error", db, step=step, message=f"{step} 超时，已跳过")
        return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": [step],
                "errors": [{"step": step, "reason": "timeout"}]}
    except Exception as exc:
        emit(run_id, "error", db, step=step, message=f"{step} 失败：{exc}")
        return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": [step],
                "errors": [{"step": step, "reason": str(exc)}]}
    count = len(result) if isinstance(result, list) else (1 if result else 0)
    emit(run_id, "step_done", db, step=step, count=count)
    return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": [step]}


# ──────────────────────────────────────────────────────
# 节点：Step 0 算法立项（带 gate）
# ──────────────────────────────────────────────────────

async def node_fanqie_positioning(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0：番茄算法立项，完成后置闸门等待确认。"""
    from app.services.bootstrap.steps.fanqie.algo_positioning import gen_algo_positioning

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="positioning", label="召开番茄算法立项会议...")
    ctx = dict(state.get("ctx") or {})
    ctx.update({"logline": state["logline"], "premise": state["premise"],
                "target_words": state["target_words"]})
    fanqie_pos = await gen_algo_positioning(svc, ctx)
    if not fanqie_pos:
        emit(run_id, "error", db, step="positioning",
             message="番茄立项定位生成失败，请更换创意或模型后重试")
        raise ValueError("fanqie_positioning_invalid")

    ctx["fanqie_positioning"] = fanqie_pos
    # 兼容通用 project 步骤：把番茄定位以通用格式写入 ctx["positioning"]
    ctx["positioning"] = _to_generic_positioning(fanqie_pos)

    emit(run_id, "step_done", db, step="positioning", count=1,
         preview=fanqie_pos.get("genre_archetype", "")[:30])
    emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
         step="positioning", positioning=fanqie_pos,
         message="请确认番茄类型公式和核心爽感后点击「继续生成」")
    _persist(
        db,
        run_id,
        {},
        gate_data={
            "kind": "positioning",
            "positioning": fanqie_pos,
            "logline": state["logline"],
            "premise": state.get("premise") or "",
            "target_words": state.get("target_words"),
        },
    )
    return {"positioning": fanqie_pos, "ctx": ctx, "completed_steps": ["positioning"]}


async def node_fanqie_gate(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0 确认闸门：支持 approve / regenerate。"""
    from app.services.bootstrap.steps.fanqie.algo_positioning import gen_algo_positioning

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
            from app.services.bootstrap.steps.fanqie.algo_positioning import gen_algo_positioning
            positioning = await gen_algo_positioning(svc, ctx)
            if not positioning:
                emit(run_id, "error", db, step="positioning",
                     message="重新生成番茄立项定位失败")
                raise ValueError("fanqie_positioning_regen_failed")
            ctx["fanqie_positioning"] = positioning
            ctx["positioning"] = _to_generic_positioning(positioning)
            emit(run_id, "step_done", db, step="positioning", count=1,
                 preview=positioning.get("genre_archetype", "")[:30])
            emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
                 step="positioning", positioning=positioning,
                 message="请再次确认番茄立项定位后继续生成")
            _persist(
                db,
                run_id,
                {},
                gate_data={
                    "kind": "positioning",
                    "positioning": positioning,
                    "logline": state["logline"],
                    "premise": state.get("premise") or "",
                    "target_words": state.get("target_words"),
                },
            )
            continue
        updated = user_input.get("positioning", positioning)
        if not isinstance(updated, dict):
            updated = positioning
        ctx["fanqie_positioning"] = updated
        ctx["positioning"] = _to_generic_positioning(updated)
        emit(run_id, "gate_passed", db, persist_status="running",
             step="positioning", positioning=updated)
        return {"positioning": updated, "ctx": ctx}


async def node_project(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 1：创建 Project 记录（复用通用 gen_project）。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="project", label="生成项目基础信息...")
    ctx = dict(state.get("ctx") or {})
    project, ctx = await gen_project(svc, ctx)
    emit(run_id, "step_done", db, step="project", count=1,
         preview=f"《{project.title}》{project.genre}")
    _persist(db, run_id, {}, project_id=str(project.id))
    return {"project_id": str(project.id), "ctx": ctx, "completed_steps": ["project"]}


# ──────────────────────────────────────────────────────
# 简单节点（各 Phase 步骤）
# ──────────────────────────────────────────────────────

async def node_contrast(s, c=None):
    from app.services.bootstrap.steps.fanqie.contrast_design import gen_contrast_design
    return await _fanqie_step(s, c, "contrast_design", "设计主角落差（越惨越爽）...", gen_contrast_design)

async def node_golden_finger(s, c=None):
    from app.services.bootstrap.steps.fanqie.golden_finger import gen_golden_finger
    return await _fanqie_step(s, c, "golden_finger", "设计金手指工程...", gen_golden_finger)

async def node_face_slap(s, c=None):
    from app.services.bootstrap.steps.fanqie.face_slap_map import gen_face_slap_map
    return await _fanqie_step(s, c, "face_slap_map", "规划打脸地图...", gen_face_slap_map)

async def node_power_ladder(s, c=None):
    from app.services.bootstrap.steps.fanqie.power_ladder import gen_power_ladder
    return await _fanqie_step(s, c, "power_ladder", "构建权力阶梯（最小化世界观）...", gen_power_ladder)

async def node_characters(s, c=None):
    from app.services.bootstrap.steps.fanqie.character_functions import gen_character_functions
    return await _fanqie_step(s, c, "characters", "生成人物功能表 + 登场序列...", gen_character_functions)

async def node_opening(s, c=None):
    from app.services.bootstrap.steps.fanqie.opening_5chapters import gen_opening_5chapters
    return await _fanqie_step(s, c, "opening_5chapters", "规划开局五章（算法生死线）...", gen_opening_5chapters)

async def node_rhythm(s, c=None):
    from app.services.bootstrap.steps.fanqie.rhythm_map import gen_rhythm_map
    return await _fanqie_step(s, c, "rhythm_map", "生成爽点节奏图 + 剧情储量池...", gen_rhythm_map)

async def node_audit(s, c=None):
    """番茄流程最后一步；完成后须 emit complete，否则前端会一直停在「生成中」。"""
    from app.services.bootstrap.steps.fanqie.signal_audit import gen_signal_audit

    patch = await _fanqie_step(
        s, c, "signal_audit", "执行番茄算法双校验...", gen_signal_audit,
    )
    config = _resolve_config(c)
    db = config["configurable"]["db"]
    run_id = s["run_id"]
    emit(
        run_id,
        "complete",
        db,
        persist_status="done",
        project_id=s.get("project_id"),
    )
    return patch


# ──────────────────────────────────────────────────────
# 构建 Fanqie StateGraph
# ──────────────────────────────────────────────────────

def _build_fanqie_graph(checkpointer) -> StateGraph:
    g = StateGraph(BootstrapState)
    for name, fn in [
        ("fanqie_positioning", node_fanqie_positioning),
        ("gate",               node_fanqie_gate),
        ("project",            node_project),
        ("contrast_design",    node_contrast),
        ("golden_finger",      node_golden_finger),
        ("face_slap_map",      node_face_slap),
        ("power_ladder",       node_power_ladder),
        ("characters",         node_characters),
        ("opening_5chapters",  node_opening),
        ("rhythm_map",         node_rhythm),
        ("signal_audit",       node_audit),
    ]:
        g.add_node(name, fn)

    chain = [
        START, "fanqie_positioning", "gate", "project",
        "contrast_design", "golden_finger", "face_slap_map",
        "power_ladder", "characters", "opening_5chapters",
        "rhythm_map", "signal_audit", END,
    ]
    for a, b in zip(chain, chain[1:]):
        g.add_edge(a, b)

    return g.compile(
        checkpointer=checkpointer,
        interrupt_before=["gate"],
    )


# ──────────────────────────────────────────────────────
# 后台任务入口
# ──────────────────────────────────────────────────────

async def run_bootstrap_fanqie(
    run_id: str, *, logline: str, premise: str, target_words: int,
    model_profile: str, llm_provider_id, user_id,
) -> None:
    """番茄模式后台任务入口；与 run_bootstrap 接口一致，仅图拓扑不同。"""
    fanqie_graph = get_fanqie_graph()
    db = SessionLocal()
    try:
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if run:
            run.status = "running"
            db.commit()
        initial: BootstrapState = {
            "run_id": run_id, "logline": logline, "premise": premise,
            "target_words": target_words, "positioning": {}, "project_id": None,
            "ctx": {}, "completed_steps": [], "errors": [],
        }
        config = {"configurable": {
            "thread_id": run_id, "db": db,
            "model_profile": model_profile,
            "llm_provider_id": llm_provider_id,
            "user_id": user_id,
        }}
        await fanqie_graph.ainvoke(initial, config=config)
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if not run or run.status != "awaiting_gate":
            _push(run_id, {"event": "__stream_end__"})
        else:
            from app.services.bootstrap.gate_auto import schedule_auto_resume_for_run

            schedule_auto_resume_for_run(run_id)
    except asyncio.CancelledError:
        emit(run_id, "cancelled", db, persist_status="cancelled", message="用户已取消生成")
        _push(run_id, {"event": "__stream_end__"})
        raise
    except Exception as exc:
        logger.exception("Fanqie bootstrap run %s failed", run_id)
        _handle_run_error(db, run_id, exc)
        _push(run_id, {"event": "__stream_end__"})
    finally:
        db.close()


async def resume_bootstrap_fanqie(
    run_id: str, resume_payload: dict, *,
    model_profile: str, llm_provider_id, user_id,
) -> None:
    """从 AsyncPostgresSaver checkpoint 继续番茄图执行。"""
    from app.services.bootstrap.gate_auto import resume_lock

    async with resume_lock(run_id):
        await _resume_bootstrap_fanqie_impl(
            run_id, resume_payload,
            model_profile=model_profile,
            llm_provider_id=llm_provider_id,
            user_id=user_id,
        )


async def _resume_bootstrap_fanqie_impl(
    run_id: str, resume_payload: dict, *,
    model_profile: str, llm_provider_id, user_id,
) -> None:
    fanqie_graph = get_fanqie_graph()
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
        await fanqie_graph.ainvoke(Command(resume=dict(resume_payload)), config=config)
    except asyncio.CancelledError:
        emit(run_id, "cancelled", db, persist_status="cancelled", message="用户已取消生成")
        raise
    except Exception as exc:
        logger.exception("Fanqie bootstrap resume %s failed", run_id)
        _handle_run_error(db, run_id, exc)
    finally:
        try:
            run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
            if run and run.status in ("done", "failed", "cancelled"):
                _push(run_id, {"event": "__stream_end__"})
            elif run and run.status == "awaiting_gate":
                from app.services.bootstrap.gate_auto import schedule_auto_resume_for_run

                schedule_auto_resume_for_run(run_id)
        except Exception:
            pass
        db.close()


# ──────────────────────────────────────────────────────
# 内部辅助
# ──────────────────────────────────────────────────────

def _to_generic_positioning(fanqie_pos: dict) -> dict:
    """
    将番茄立项定位转换为通用 positioning 格式，
    供 gen_project 等复用步骤读取（不影响番茄专属字段）。
    """
    return {
        "target_audience": f"番茄男频·{fanqie_pos.get('genre_archetype', '')}读者",
        "tropes": fanqie_pos.get("platform_tags", []),
        "reference_works": fanqie_pos.get("competitor_works", []),
        "selling_point": fanqie_pos.get("algo_hook", ""),
        "face_slap_pattern": "每3章一小打，每10章一大打",
        "emotional_arc": "番茄爽文情绪曲线：压抑→爆发→余韵",
        "pace_type": "fast",
        "taboo_lines": fanqie_pos.get("taboo_check", "") and [str(fanqie_pos["taboo_check"])] or ["无"],
    }
