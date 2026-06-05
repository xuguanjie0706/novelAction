"""
Bootstrap LangGraph StateGraph — 支持 human-in-the-loop 闸门。

拆分结构：
  - graph_sse.py: SSE 事件推送与持久化（subscribe / unsubscribe / emit / push / persist）
  - graph_runner.py: 后台任务入口（run_bootstrap / resume_bootstrap）
  - 本文件: State 定义 + 节点函数 + _build_graph 拓扑 + checkpointer 初始化

拓扑：START → positioning → gate(interrupt) → project → power_systems → gate_power(interrupt)
      → factions → storylines → antagonist_ladder → characters → gate_chars(interrupt) → skills_items → settings
      → volumes → gate_vol(interrupt) → emotion_arc → villain_arc
      → memory → relations → core_mysteries → opening_contract → consistency → END

Checkpointing：AsyncPostgresSaver（psycopg3 异步连接池，thread_id=run_id）。
由 main.py _on_startup 调用 init_bootstrap_graph() 完成初始化，checkpoint 持久化到
同一 PostgreSQL 实例，重启 / 多 worker 均可安全 resume，无需 restore_bootstrap_checkpoint_if_lost。
"""
from __future__ import annotations

import asyncio
import logging
from operator import add
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict

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
# 全局 bootstrap_graph（由 init_bootstrap_graph 在 startup 完成初始化）
# ──────────────────────────────────────────────────────
bootstrap_graph = None  # type: ignore[assignment]
fanqie_graph = None     # type: ignore[assignment]
_pg_pool = None         # AsyncConnectionPool，供优雅关闭使用


def get_bootstrap_graph():
    """返回已初始化的 bootstrap_graph；startup 前调用则抛 RuntimeError。"""
    if bootstrap_graph is None:
        raise RuntimeError(
            "bootstrap_graph 尚未初始化，请确认 init_bootstrap_graph() 已在 startup 中被 await。"
        )
    return bootstrap_graph


def get_fanqie_graph():
    """返回已初始化的 fanqie_graph（番茄专属拓扑，与主图共用 AsyncPostgresSaver）。"""
    if fanqie_graph is None:
        raise RuntimeError(
            "fanqie_graph 尚未初始化，请确认 init_bootstrap_graph() 已在 startup 中被 await。"
        )
    return fanqie_graph


def get_fanfic_graph():
    """返回已初始化的 fanfic_graph（同人·番茄拓扑）。"""
    if fanfic_graph is None:
        raise RuntimeError(
            "fanfic_graph 尚未初始化，请确认 init_bootstrap_graph() 已在 startup 中被 await。"
        )
    return fanfic_graph


def get_graph_for_mode(mode: str):
    """按 BootstrapRun.mode 返回对应 CompiledGraph。"""
    if mode == "fanqie":
        return get_fanqie_graph()
    if mode == "fanfic":
        return get_fanfic_graph()
    return get_bootstrap_graph()


async def init_bootstrap_graph(pg_conn_string: str) -> None:
    """在 FastAPI startup 中调用：创建 psycopg3 异步连接池 + AsyncPostgresSaver，
    建立 checkpoint 表（幂等），按 STYLE_REGISTRY 编译三套 CompiledGraph。

    Args:
        pg_conn_string: PostgreSQL DSN，例如 "postgresql://user:pw@host:5432/db"。
                        psycopg3 直接接受标准 DSN，无需 +psycopg 前缀。
    """
    global bootstrap_graph, fanqie_graph, fanfic_graph, _pg_pool

    from psycopg_pool import AsyncConnectionPool
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from app.services.bootstrap.pipeline import build_graph
    from app.services.bootstrap.pipeline.styles import STYLE_REGISTRY

    _pg_pool = AsyncConnectionPool(
        conninfo=pg_conn_string,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    await _pg_pool.open()

    checkpointer = AsyncPostgresSaver(_pg_pool)
    await checkpointer.setup()

    bootstrap_graph = build_graph(
        STYLE_REGISTRY["sequential"], checkpointer, state_type=BootstrapState,
    )
    fanqie_graph = build_graph(
        STYLE_REGISTRY["fanqie"], checkpointer, state_type=BootstrapState,
    )
    fanfic_graph = build_graph(
        STYLE_REGISTRY["fanfic"], checkpointer, state_type=BootstrapState,
    )
    logger.info(
        "bootstrap_graph / fanqie_graph / fanfic_graph 初始化完成（PipelineBuilder + AsyncPostgresSaver）"
    )


async def close_bootstrap_graph() -> None:
    """在 FastAPI shutdown 中调用，优雅关闭连接池。"""
    global bootstrap_graph, fanqie_graph, fanfic_graph, _pg_pool
    if _pg_pool is not None:
        await _pg_pool.close()
        _pg_pool = None
    bootstrap_graph = None
    fanqie_graph = None
    fanfic_graph = None
    logger.info("bootstrap_graph pg_pool 已关闭")


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
    """已废弃：AsyncPostgresSaver 持久化到 PG，checkpoint 不会随进程重启丢失，无需手动恢复。
    保留函数签名以避免旧调用点 ImportError；直接返回 False（表示无需恢复）。

    .. deprecated::
        切换到 AsyncPostgresSaver 后此函数为空壳，graph_runner.py 已不再调用。
    """
    logger.debug("restore_bootstrap_checkpoint_if_lost called but skipped (AsyncPostgresSaver active)")
    return False


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
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    ctx = sanitize_bootstrap_ctx(dict(state.get("ctx") or {}))
    ctx.update({"logline": state["logline"], "premise": state["premise"],
                "target_words": state["target_words"]})

    emit(run_id, "step_start", db, step="positioning", label="召开立项会议（题材定位）...")
    positioning = await svc._gen_positioning(ctx)
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


