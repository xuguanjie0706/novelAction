"""
Bootstrap LangGraph StateGraph — 支持 human-in-the-loop 闸门。

拓扑：START → positioning → gate(interrupt) → project → power_systems → gate_power(interrupt)
      → factions → storylines → characters → gate_chars(interrupt) → skills_items → settings
      → volumes → gate_vol(interrupt) → emotion_arc → villain_arc
      → memory → relations → core_mysteries → opening_contract → vol1_chapters
      → ch1_scenes → consistency → END

多个 ``interrupt_before`` 与节点内 ``interrupt()`` 配合：每道闸门先落库/推送 ``gate_pending``，
用户 ``POST /resume`` 后继续；Step0 支持 ``action=regenerate`` 重跑立项；Step2/5/9 支持删表重跑。

Checkpointing：进程内 MemorySaver（thread_id=run_id）；多 worker 需换 PostgresSaver。
复杂节点实现见 graph_nodes.py。代码红线：本文件 < 400 行。
"""
from __future__ import annotations

import asyncio
import logging
import time
from operator import add
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_config
from langgraph.types import interrupt, Command

from app.database import SessionLocal
from app.models.bootstrap_run import BootstrapRun

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────
# 全局 Checkpointer（进程内单例；thread_id = run_id）
# ──────────────────────────────────────────────────────
_checkpointer = MemorySaver()

# ──────────────────────────────────────────────────────
# SSE 事件扇出注册表
# ──────────────────────────────────────────────────────
_queue_registry: dict[str, list[asyncio.Queue]] = {}


def subscribe(run_id: str) -> asyncio.Queue:
    """注册 SSE 订阅 Queue，供 /events 端点消费。每个 item 是 event dict。"""
    q: asyncio.Queue = asyncio.Queue(maxsize=512)
    _queue_registry.setdefault(run_id, []).append(q)
    return q


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    """SSE 断开后注销 Queue，防止内存泄漏。"""
    subs = _queue_registry.get(run_id, [])
    if q in subs:
        subs.remove(q)


def _push(run_id: str, payload: dict) -> None:
    """同步 push 到所有订阅队列（满则丢弃，不阻塞图执行）。"""
    for q in _queue_registry.get(run_id, []):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for run %s, dropping %s", run_id, payload.get("event"))


def _persist(db, run_id: str, payload: dict, *, status: str | None = None, **extra) -> None:
    """追加 event 到 BootstrapRun.events；可同时更新 status 等字段。"""
    try:
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if not run:
            return
        if payload:
            run.events = list(run.events or []) + [payload]
        if status:
            run.status = status
        for k, v in extra.items():
            setattr(run, k, v)
        db.commit()
    except Exception:
        logger.exception("Failed to persist event for run %s", run_id)
        db.rollback()


def emit(run_id: str, event: str, db=None, *, persist_status: str | None = None, **kwargs) -> None:
    """推送 SSE 事件：写实时队列 + 可选持久化到 BootstrapRun.events / 更新 status。"""
    # 服务端毫秒时间戳：供前端重连 replay 时还原各步耗时（放在最后，避免 kwargs 覆盖）
    payload = {"event": event, **kwargs, "ts": int(time.time() * 1000)}
    _push(run_id, payload)
    if db is not None:
        _persist(db, run_id, payload, status=persist_status)


# ──────────────────────────────────────────────────────
# Graph State
# ──────────────────────────────────────────────────────

class BootstrapState(TypedDict):
    """LangGraph 全局状态；节点返回需更新的字段子集。"""
    # 输入（图启动时写入，节点只读）
    run_id: str
    logline: str
    premise: str
    target_words: int
    # Step 0
    positioning: dict
    # Step 1
    project_id: Optional[str]
    # 跨步骤累积上下文（与原 _sequential ctx 兼容）
    ctx: dict
    # 追加型字段（LangGraph reducer: operator.add）
    completed_steps: Annotated[list[str], add]
    errors: Annotated[list[dict], add]


# ──────────────────────────────────────────────────────
# 依赖注入辅助
# ──────────────────────────────────────────────────────

def _resolve_config(config: dict | None) -> dict:
    """兼容不同 LangGraph 运行时：优先显式 config，其次从上下文读取。"""
    return config or get_config()


def _make_svc(config: dict | None):
    """从 RunnableConfig.configurable 构建 GenerationService（含 db + AIService）。"""
    config = _resolve_config(config)
    c = config.get("configurable", {})
    from app.services.generation_service import GenerationService
    return GenerationService(
        db=c["db"],
        model_profile=c.get("model_profile", "gemini"),
        llm_provider_id=c.get("llm_provider_id"),
        user_id=c.get("user_id"),
    )


# ──────────────────────────────────────────────────────
# 通用薄步骤执行器（简单节点 1 行调用即可）
# ──────────────────────────────────────────────────────

async def _run_step(state: BootstrapState, config: dict | None,
                    step: str, label: str, fn_name: str, **fn_kwargs) -> dict:
    """emit start → svc.<fn_name>(project, ctx) → emit done；超时/异常跳过不中断图。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step=step, label=label)
    ctx = dict(state.get("ctx") or {})
    from app.models import Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()
    try:
        result = await asyncio.wait_for(
            getattr(svc, fn_name)(project, ctx, **fn_kwargs),
            timeout=300.0,
        )
    except asyncio.TimeoutError:
        emit(run_id, "error", db, step=step, message=f"{step} 超时，已跳过")
        return {"ctx": ctx, "completed_steps": [step], "errors": [{"step": step, "reason": "timeout"}]}
    except Exception as exc:
        emit(run_id, "error", db, step=step, message=f"{step} 失败：{exc}")
        return {"ctx": ctx, "completed_steps": [step], "errors": [{"step": step, "reason": str(exc)}]}
    count = len(result) if isinstance(result, list) else (1 if result else 0)
    emit(run_id, "step_done", db, step=step, count=count)
    return {"ctx": ctx, "completed_steps": [step]}


# ──────────────────────────────────────────────────────
# 节点：positioning / gate / project（含特殊逻辑，保留在本文件）
# ──────────────────────────────────────────────────────

async def node_positioning(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0：立项会议。完成后置 status=awaiting_gate 并推送 gate_pending 给前端。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="positioning", label="召开立项会议（题材定位）...")
    ctx = dict(state.get("ctx") or {})
    ctx.update({"logline": state["logline"], "premise": state["premise"],
                "target_words": state["target_words"]})
    positioning = await svc._gen_positioning(ctx)
    if not positioning:
        emit(run_id, "error", db, step="positioning",
             message="立项定位生成未通过 schema 校验（已重试），请更换模型或精简创意后重试")
        raise ValueError("positioning_invalid")
    ctx["positioning"] = positioning
    emit(run_id, "step_done", db, step="positioning", count=1,
         preview=(positioning.get("selling_point") or "")[:30])
    emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
         step="positioning", positioning=positioning,
         message="请确认或修改立项定位后点击「继续生成」")
    _persist(db, run_id, {}, gate_data={"kind": "positioning", "positioning": positioning})
    return {"positioning": positioning, "ctx": ctx, "completed_steps": ["positioning"]}


async def node_gate(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0 后闸门：确认 / 编辑 / 重新召开立项会议（regenerate）。"""
    from langgraph.types import interrupt

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    positioning = dict(state.get("positioning") or {})
    ctx = dict(state.get("ctx") or {})

    while True:
        user_input: Any = interrupt({
            "type": "positioning_gate",
            "step": "positioning",
            "positioning": positioning,
        })
        if not isinstance(user_input, dict):
            user_input = {}
        action = (user_input.get("action") or "approve").strip().lower()
        if action == "regenerate":
            ctx = dict(state.get("ctx") or {})
            ctx.update({
                "logline": state["logline"],
                "premise": state["premise"],
                "target_words": state["target_words"],
            })
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
            _persist(db, run_id, {}, gate_data={"kind": "positioning", "positioning": positioning})
            continue
        updated = user_input.get("positioning", positioning)
        if not isinstance(updated, dict):
            updated = positioning
        ctx["positioning"] = updated
        emit(run_id, "gate_passed", db, persist_status="running",
             step="positioning", positioning=updated)
        return {"positioning": updated, "ctx": ctx}


async def node_project(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 1：生成项目基础信息并落库，回填 BootstrapRun.project_id。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = state["run_id"]
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="project", label="生成项目基础信息...")
    ctx = dict(state.get("ctx") or {})
    project, ctx = await svc._gen_project(ctx)
    emit(run_id, "step_done", db, step="project", count=1,
         preview=f"《{project.title}》{project.genre}")
    _persist(db, run_id, {}, project_id=str(project.id))
    return {"project_id": str(project.id), "ctx": ctx, "completed_steps": ["project"]}


# ──────────────────────────────────────────────────────
# 简单节点（委托 _run_step，1 行每个）
# ──────────────────────────────────────────────────────

async def node_power_systems(s, c=None): return await _run_step(s, c, "power_systems", "生成境界体系...", "_gen_power_systems")  # noqa: E501
async def node_factions(s, c=None):      return await _run_step(s, c, "factions",      "生成势力体系...", "_gen_factions")       # noqa: E501
async def node_storylines(s, c=None):    return await _run_step(s, c, "storylines",    "生成故事线...",   "_gen_storylines")     # noqa: E501
async def node_settings(s, c=None):      return await _run_step(s, c, "settings",      "生成世界观设定卡...", "_gen_settings")   # noqa: E501
async def node_memory(s, c=None):          return await _run_step(s, c, "memory",          "生成记忆库种子...",      "_gen_memory")           # noqa: E501
async def node_opening_contract(s, c=None): return await _run_step(s, c, "opening_contract", "规划开局追读承诺...",  "_gen_opening_contract")  # noqa: E501
async def node_emotion_arc(s, c=None):     return await _run_step(s, c, "emotion_arc",     "规划全书情绪节律...",    "_gen_emotion_arc")       # noqa: E501
async def node_villain_arc(s, c=None):     return await _run_step(s, c, "villain_arc",     "生成反派独立行动线...", "_gen_villain_arc")       # noqa: E501
async def node_core_mysteries(s, c=None):  return await _run_step(s, c, "core_mysteries",  "预分配全书核心谜题...", "_gen_core_mysteries")    # noqa: E501


# ──────────────────────────────────────────────────────
# 构建 StateGraph
# ──────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    from app.services.bootstrap.graph_nodes import (
        node_characters, node_skills_items, node_volumes,
        node_relations, node_vol1_chapters, node_ch1_scenes, node_consistency,
    )
    from app.services.bootstrap.graph_gates import (
        node_gate_characters,
        node_gate_power_systems,
        node_gate_volumes,
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
        ("characters",           node_characters),
        ("gate_characters",      node_gate_characters),
        ("skills_items",         node_skills_items),
        ("settings",             node_settings),
        ("volumes",              node_volumes),
        ("gate_volumes",         node_gate_volumes),
        ("emotion_arc",          node_emotion_arc),
        ("villain_arc",          node_villain_arc),
        ("memory",               node_memory),
        ("relations",            node_relations),
        ("core_mysteries",       node_core_mysteries),
        ("opening_contract",     node_opening_contract),
        ("vol1_chapters",        node_vol1_chapters),
        ("ch1_scenes",           node_ch1_scenes),
        ("consistency",          node_consistency),
    ]:
        g.add_node(name, fn)

    chain = [
        START, "positioning", "gate", "project",
        "power_systems", "gate_power_systems", "factions", "storylines",
        "characters", "gate_characters", "skills_items", "settings",
        "volumes", "gate_volumes", "emotion_arc", "villain_arc",
        "memory", "relations", "core_mysteries",
        "opening_contract", "vol1_chapters",
        "ch1_scenes", "consistency", END,
    ]
    for a, b in zip(chain, chain[1:]):
        g.add_edge(a, b)

    return g.compile(
        checkpointer=_checkpointer,
        # 仅 Step0 前暂停：positioning 节点已推送 gate_pending。
        # Step2/5/9 闸门完全依赖各 gate 节点内的 interrupt()，否则 interrupt_before
        # 会在 emit(gate_pending) 之前截断，前端永远收不到闸门事件。
        interrupt_before=["gate"],
    )


bootstrap_graph = _build_graph()


# ──────────────────────────────────────────────────────
# 后台任务入口
# ──────────────────────────────────────────────────────

async def run_bootstrap(
    run_id: str, *, logline: str, premise: str, target_words: int,
    model_profile: str, llm_provider_id, user_id,
) -> None:
    """后台任务：执行图至 gate interrupt 暂停；resume 由 resume_bootstrap() 继续。"""
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
        await bootstrap_graph.ainvoke(initial, config=config)
        # graph 在 gate interrupt 处正常返回（非异常）；此时不关闭 SSE 流，
        # 让前端 SSE 连接保持活跃，等待 resume_bootstrap() 继续推送事件。
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if not run or run.status != "awaiting_gate":
            _push(run_id, {"event": "__stream_end__"})
    except asyncio.CancelledError:
        emit(run_id, "cancelled", db, persist_status="cancelled", message="用户已取消生成")
        _push(run_id, {"event": "__stream_end__"})
        raise
    except Exception as exc:
        logger.exception("Bootstrap run %s failed", run_id)
        _handle_run_error(db, run_id, exc)
        _push(run_id, {"event": "__stream_end__"})
    finally:
        db.close()


async def resume_bootstrap(
    run_id: str,
    resume_payload: dict,
    *,
    model_profile: str,
    llm_provider_id,
    user_id,
) -> None:
    """从 MemorySaver checkpoint 继续，以 Command(resume=...) 传入用户决策（含多闸门）。"""
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
        await bootstrap_graph.ainvoke(
            Command(resume=dict(resume_payload)),
            config=config,
        )
    except asyncio.CancelledError:
        emit(run_id, "cancelled", db, persist_status="cancelled", message="用户已取消生成")
        raise
    except Exception as exc:
        logger.exception("Bootstrap resume %s failed", run_id)
        _handle_run_error(db, run_id, exc)
    finally:
        # 多闸门：若本轮 ainvoke 停在 interrupt()（status=awaiting_gate），必须保持 SSE 连接，
        # 等待用户下一次 /resume；仅在终态时关闭流。
        try:
            run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
            if run and run.status in ("done", "failed", "cancelled"):
                _push(run_id, {"event": "__stream_end__"})
        except Exception:
            pass
        db.close()


def _handle_run_error(db, run_id: str, exc: Exception) -> None:
    """更新 DB 状态为 failed 并推送 error 事件（内部辅助，不抛出）。"""
    try:
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if run:
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            db.commit()
        emit(run_id, "error", message=str(exc))
    except Exception:
        pass
