"""
Bootstrap LangGraph StateGraph — 支持 human-in-the-loop 闸门。

拆分结构：
  - graph_sse.py: SSE 事件推送与持久化（subscribe / unsubscribe / emit / push / persist）
  - graph_runner.py: 后台任务入口（run_bootstrap / resume_bootstrap）
  - 本文件: State 定义 + 节点函数 + _build_graph 拓扑 + checkpoint 恢复

拓扑：START → positioning → gate(interrupt) → project → power_systems → gate_power(interrupt)
      → factions → storylines → antagonist_ladder → characters → gate_chars(interrupt) → skills_items → settings
      → volumes → gate_vol(interrupt) → emotion_arc → villain_arc
      → memory → relations → core_mysteries → opening_contract → consistency → END

Checkpointing：进程内 MemorySaver（thread_id=run_id）；多 worker 需换 PostgresSaver。
"""
from __future__ import annotations

import asyncio
import logging
from operator import add
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_config
from langgraph.types import interrupt, Command

from app.models.bootstrap_run import BootstrapRun

# ── re-export：保持外部 import 路径不变 ──────────────────────────
from app.services.bootstrap.graph_ctx import sanitize_bootstrap_ctx
from app.services.bootstrap.graph_sse import (  # noqa: F401
    subscribe, unsubscribe, emit, push as _push, persist as _persist,
)
from app.services.bootstrap.graph_runner import (  # noqa: F401
    run_bootstrap, resume_bootstrap, _handle_run_error,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────
# 全局 Checkpointer（进程内单例；thread_id = run_id）
# ──────────────────────────────────────────────────────
_checkpointer = MemorySaver()


# ──────────────────────────────────────────────────────
# Graph State
# ──────────────────────────────────────────────────────

class BootstrapState(TypedDict):
    """LangGraph 全局状态；节点返回需更新的字段子集。"""
    run_id: str
    logline: str
    premise: str
    target_words: int
    positioning: dict
    project_id: Optional[str]
    ctx: dict
    completed_steps: Annotated[list[str], add]
    errors: Annotated[list[dict], add]


# ──────────────────────────────────────────────────────
# 依赖注入辅助
# ──────────────────────────────────────────────────────

def _resolve_config(config: dict | None) -> dict:
    return config or get_config()


def _state_run_id(state: BootstrapState | dict | None, config: dict | None) -> str:
    rid = (state or {}).get("run_id")
    if rid:
        return str(rid)
    cfg = _resolve_config(config).get("configurable", {})
    return str(cfg.get("thread_id") or "")


def restore_bootstrap_checkpoint_if_lost(
    graph, *, run_id: str, run: BootstrapRun, config: dict,
    positioning_node: str = "positioning",
) -> bool:
    """MemorySaver 随进程重启清空；awaiting_gate 的 resume 需从 DB 还原 checkpoint。"""
    snap = graph.get_state(config)
    values = (snap.values or {}) if snap else {}
    if values.get("run_id"):
        return False

    gd = run.gate_data if isinstance(run.gate_data, dict) else {}
    positioning = gd.get("positioning") or {}
    logline = run.logline or gd.get("logline") or ""
    premise = gd.get("premise") or ""
    target_words = int(gd.get("target_words") or 1_000_000)
    project_id = str(run.project_id) if run.project_id else None

    from app.services.bootstrap.graph_recovery import rebuild_ctx_from_db
    db = config["configurable"]["db"]
    ctx = sanitize_bootstrap_ctx(
        rebuild_ctx_from_db(db, project_id or "", gd, logline, premise, target_words),
    )

    _COMPLETED_BEFORE_MEMORY = [
        "positioning", "project", "power_systems", "factions", "storylines",
        "antagonist_ladder", "characters", "skills", "items", "settings", "volumes",
        "emotion_arc", "villain_arc",
    ]
    gate_to_completed: dict[str, list[str]] = {
        "positioning":        ["positioning"],
        "gate_power_systems": ["positioning", "project", "power_systems"],
        "gate_characters":    ["positioning", "project", "power_systems", "factions",
                               "storylines", "antagonist_ladder", "characters"],
        "gate_volumes":       ["positioning", "project", "power_systems", "factions",
                               "storylines", "antagonist_ladder", "characters", "skills", "items", "settings", "volumes"],
    }
    _STEP_TO_NODE: dict[str, str] = {
        "memory": "memory_relations",
        "relations": "memory_relations",
        "emotion_arc": "emotion_villain",
        "villain_arc": "emotion_villain",
        "consistency": "consistency",
        "core_mysteries": "core_mysteries",
        "opening_contract": "opening_contract",
    }
    if gd.get("kind") == "step_retry":
        failed_step = str(gd.get("step") or "memory")
        resume_node = _STEP_TO_NODE.get(failed_step, "memory_relations")
        completed = list(_COMPLETED_BEFORE_MEMORY)
        if failed_step == "relations":
            completed = completed + ["memory"]
        restore_label = f"step_retry:{failed_step}"
    else:
        current_gate = gd.get("current_gate") or "positioning"
        completed = gate_to_completed.get(current_gate, ["positioning"])
        gate_to_resume_node: dict[str, str] = {
            "positioning":        positioning_node,
            "gate_power_systems": "gate_power_systems",
            "gate_characters":    "gate_characters",
            "gate_volumes":       "gate_volumes",
        }
        resume_node = gate_to_resume_node.get(current_gate, positioning_node)
        restore_label = str(current_gate)

    recovery: BootstrapState = {
        "run_id": run_id, "logline": logline, "premise": premise,
        "target_words": target_words, "positioning": positioning,
        "project_id": project_id, "ctx": ctx,
        "completed_steps": completed, "errors": [],
    }
    graph.update_state(config, recovery, as_node=resume_node)
    logger.warning(
        "Restored bootstrap checkpoint for run %s from DB "
        "(in-memory checkpointer was empty; restore=%s resume_node=%s)",
        run_id, restore_label, resume_node,
    )
    return True


def _make_svc(config: dict | None):
    """从 RunnableConfig.configurable 构建 GenerationService。"""
    config = _resolve_config(config)
    c = config.get("configurable", {})
    from app.services.generation_service import GenerationService
    return GenerationService(
        db=c["db"], model_profile=c.get("model_profile", "gemini"),
        llm_provider_id=c.get("llm_provider_id"), user_id=c.get("user_id"),
    )


# ──────────────────────────────────────────────────────
# 通用薄步骤执行器
# ──────────────────────────────────────────────────────

async def _run_step(state: BootstrapState, config: dict | None,
                    step: str, label: str, fn_name: str, **fn_kwargs) -> dict:
    """emit start → svc.<fn_name> → emit done；失败则 interrupt 等待用户重试。"""
    from app.services.bootstrap.step_failure import pause_for_step_retry, user_wants_step_retry
    from app.services.llm_errors import format_llm_error_message

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    ctx = sanitize_bootstrap_ctx(dict(state.get("ctx") or {}))
    from app.models import Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    while True:
        emit(run_id, "step_start", db, step=step, label=label)
        try:
            result = await asyncio.wait_for(
                getattr(svc, fn_name)(project, ctx, **fn_kwargs), timeout=300.0,
            )
        except asyncio.TimeoutError:
            msg = f"{step} 超时（5 分钟），请重试或检查模型线路"
        except Exception as exc:
            msg = format_llm_error_message(exc)
        else:
            if isinstance(result, list):
                count = len(result)
            elif isinstance(result, dict):
                from app.services.bootstrap.opening_contract_io import _contract_field_count
                count = _contract_field_count(result)
            else:
                count = 1 if result else 0
            emit(run_id, "step_done", db, step=step, count=count)
            return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": [step]}

        user = await pause_for_step_retry(state, config, step=step, message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": sanitize_bootstrap_ctx(ctx), "errors": [{"step": step, "reason": msg}]}


# ──────────────────────────────────────────────────────
# 节点：positioning / gate / project
# ──────────────────────────────────────────────────────

async def node_positioning(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0：立项会议。"""
    from app.services.bootstrap.step_failure import pause_for_step_retry, user_wants_step_retry

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    ctx = sanitize_bootstrap_ctx(dict(state.get("ctx") or {}))
    ctx.update({"logline": state["logline"], "premise": state["premise"],
                "target_words": state["target_words"]})

    while True:
        emit(run_id, "step_start", db, step="positioning", label="召开立项会议（题材定位）...")
        positioning = await svc._gen_positioning(ctx)
        if positioning:
            break
        msg = "立项定位生成未通过 schema 校验（已重试 3 次），请更换模型或精简创意后重试"
        emit(run_id, "error", db, step="positioning", message=msg)
        user = await pause_for_step_retry(state, config, step="positioning", message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": sanitize_bootstrap_ctx(ctx), "errors": [{"step": "positioning", "reason": msg}]}

    ctx["positioning"] = positioning
    emit(run_id, "step_done", db, step="positioning", count=1,
         preview=(positioning.get("selling_point") or "")[:30])
    emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
         step="positioning", positioning=positioning,
         message="请确认或修改立项定位后点击「继续生成」")
    _persist(db, run_id, {}, gate_data={
        "kind": "positioning", "positioning": positioning,
        "logline": state["logline"], "premise": state.get("premise") or "",
        "target_words": state.get("target_words"),
    })
    return {
        "positioning": positioning,
        "ctx": sanitize_bootstrap_ctx(ctx),
        "completed_steps": ["positioning"],
    }


async def node_gate(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0 后闸门：确认 / 编辑 / 重新召开立项会议（regenerate）。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    positioning = dict(state.get("positioning") or {})
    ctx = sanitize_bootstrap_ctx(dict(state.get("ctx") or {}))

    while True:
        user_input: Any = interrupt({
            "type": "positioning_gate", "step": "positioning", "positioning": positioning,
        })
        if not isinstance(user_input, dict):
            user_input = {}
        action = (user_input.get("action") or "approve").strip().lower()
        if action == "regenerate":
            ctx = dict(state.get("ctx") or {})
            ctx.update({"logline": state["logline"], "premise": state["premise"],
                        "target_words": state["target_words"]})
            positioning = await svc._gen_positioning(ctx)
            if not positioning:
                emit(run_id, "error", db, step="positioning",
                     message="重新生成立项定位失败，请稍后重试")
                raise ValueError("positioning_regen_failed")
            ctx["positioning"] = positioning
            emit(run_id, "step_start", db, step="positioning", label="重新召开立项会议…")
            emit(run_id, "step_done", db, step="positioning", count=1,
                 preview=(positioning.get("selling_point") or "")[:30])
            emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
                 step="positioning", positioning=positioning,
                 message="请再次确认或修改立项定位后继续生成")
            _persist(db, run_id, {}, gate_data={
                "kind": "positioning", "positioning": positioning,
                "logline": state["logline"], "premise": state.get("premise") or "",
                "target_words": state.get("target_words"),
            })
            continue
        if action == "select_candidate":
            idx = user_input.get("index", 0)
            cands = positioning.get("candidates") or []
            if isinstance(idx, int) and 0 <= idx < len(cands):
                from app.schemas.bootstrap_positioning import try_validate_positioning
                norm, _ = try_validate_positioning(cands[idx])
                selected_flat = norm or dict(cands[idx])
                selected_flat["candidates"] = cands
                selected_flat["auto_selected_index"] = positioning.get("auto_selected_index", 0)
                selected_flat["auto_selection_reason"] = positioning.get("auto_selection_reason", "")
                selected_flat["auto_selection_comparison"] = positioning.get("auto_selection_comparison", "")
                updated = selected_flat
            else:
                updated = positioning
        else:
            updated = user_input.get("positioning", positioning)
            if not isinstance(updated, dict):
                updated = positioning
        ctx["positioning"] = updated
        emit(run_id, "gate_passed", db, persist_status="running",
             step="positioning", positioning=updated)
        return {"positioning": updated, "ctx": sanitize_bootstrap_ctx(ctx)}


async def node_project(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 1：生成项目基础信息并落库。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="project", label="生成项目基础信息...")
    ctx = sanitize_bootstrap_ctx(dict(state.get("ctx") or {}))
    project, ctx = await svc._gen_project(ctx)
    emit(run_id, "step_done", db, step="project", count=1,
         preview=f"《{project.title}》{project.genre}")
    _persist(db, run_id, {}, project_id=str(project.id))
    return {
        "project_id": str(project.id),
        "ctx": sanitize_bootstrap_ctx(ctx),
        "completed_steps": ["project"],
    }


# ──────────────────────────────────────────────────────
# 简单节点（委托 _run_step）
# ──────────────────────────────────────────────────────

async def node_power_systems(s, c=None): return await _run_step(s, c, "power_systems", "生成境界体系...", "_gen_power_systems")  # noqa: E501
async def node_factions(s, c=None):      return await _run_step(s, c, "factions",      "生成势力体系...", "_gen_factions")       # noqa: E501
async def node_storylines(s, c=None):    return await _run_step(s, c, "storylines",    "生成故事线...",   "_gen_storylines")     # noqa: E501
async def node_antagonist_ladder(s, c=None): return await _run_step(s, c, "antagonist_ladder", "规划卷级对立面阶梯...", "_gen_antagonist_ladder")  # noqa: E501
async def node_settings(s, c=None):      return await _run_step(s, c, "settings",      "生成世界观设定卡...", "_gen_settings")   # noqa: E501
async def node_opening_contract(s, c=None): return await _run_step(s, c, "opening_contract", "规划开局追读承诺...", "_gen_opening_contract")   # noqa: E501
async def node_core_mysteries(s, c=None):   return await _run_step(s, c, "core_mysteries",   "预分配全书核心谜题...", "_gen_core_mysteries")    # noqa: E501


# ──────────────────────────────────────────────────────
# 构建 StateGraph
# ──────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    from app.services.bootstrap.graph_nodes import (
        node_characters, node_skills_items, node_volumes,
        node_consistency, node_emotion_villain, node_memory_relations,
    )
    from app.services.bootstrap.graph_gates import (
        node_gate_characters, node_gate_power_systems, node_gate_volumes,
    )
    g = StateGraph(BootstrapState)
    for name, fn in [
        ("positioning",          node_positioning),
        ("gate",                 node_gate),
        ("project",              node_project),
        ("power_systems",        node_power_systems),
        ("gate_power_systems",   node_gate_power_systems),
        ("factions",             node_factions),
        ("storylines",           node_storylines),
        ("antagonist_ladder",    node_antagonist_ladder),
        ("characters",           node_characters),
        ("gate_characters",      node_gate_characters),
        ("skills_items",         node_skills_items),
        ("settings",             node_settings),
        ("volumes",              node_volumes),
        ("gate_volumes",         node_gate_volumes),
        ("emotion_villain",      node_emotion_villain),
        ("memory_relations",     node_memory_relations),
        ("core_mysteries",       node_core_mysteries),
        ("opening_contract",     node_opening_contract),
        ("consistency",          node_consistency),
    ]:
        g.add_node(name, fn)

    chain = [
        START, "positioning", "gate", "project",
        "power_systems", "gate_power_systems", "factions", "storylines",
        "antagonist_ladder", "characters", "gate_characters", "skills_items", "settings",
        "volumes", "gate_volumes",
        "emotion_villain", "memory_relations", "core_mysteries",
        "opening_contract", "consistency", END,
    ]
    for a, b in zip(chain, chain[1:]):
        g.add_edge(a, b)

    return g.compile(
        checkpointer=_checkpointer,
        interrupt_before=["gate"],
    )


bootstrap_graph = _build_graph()
