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


def _state_run_id(state: BootstrapState | dict | None, config: dict | None) -> str:
    """从图状态或 configurable.thread_id 解析 run_id（resume 丢 checkpoint 时的兜底）。"""
    rid = (state or {}).get("run_id")
    if rid:
        return str(rid)
    cfg = _resolve_config(config).get("configurable", {})
    return str(cfg.get("thread_id") or "")


def restore_bootstrap_checkpoint_if_lost(
    graph,
    *,
    run_id: str,
    run: BootstrapRun,
    config: dict,
    positioning_node: str = "positioning",
) -> bool:
    """MemorySaver 随进程重启清空；awaiting_gate 的 resume 需从 DB 还原 checkpoint。

    根据 gate_data.current_gate 判断暂停位置，从 DB 重建尽量完整的 ctx，
    避免 resume 后后续步骤因 ctx 字段缺失而静默出错。

    Returns:
        True 表示已从 BootstrapRun 写入 checkpoint。
    """
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

    # 当前暂停所在的 gate 节点名（由各 gate 写入 gate_data）
    current_gate = gd.get("current_gate") or "positioning"

    # 从 DB 重建完整 ctx（实现见 graph_recovery.py，保持本文件 < 600 行）
    from app.services.bootstrap.graph_recovery import rebuild_ctx_from_db
    db = config["configurable"]["db"]
    ctx = rebuild_ctx_from_db(db, project_id or "", gd, logline, premise, target_words)

    # completed_steps 根据 current_gate 推断
    gate_to_completed: dict[str, list[str]] = {
        "positioning":        ["positioning"],
        "gate_power_systems": ["positioning", "project", "power_systems"],
        "gate_characters":    ["positioning", "project", "power_systems", "factions",
                               "storylines", "characters"],
        "gate_volumes":       ["positioning", "project", "power_systems", "factions",
                               "storylines", "characters", "skills", "items", "settings", "volumes"],
    }
    completed = gate_to_completed.get(current_gate, ["positioning"])

    # as_node 决定 LangGraph 从哪个节点继续；gate 节点内部会 interrupt()，
    # update_state 写入 gate 前一个普通节点可确保图能走到 interrupt 处。
    gate_to_resume_node: dict[str, str] = {
        "positioning":        positioning_node,
        "gate_power_systems": "gate_power_systems",
        "gate_characters":    "gate_characters",
        "gate_volumes":       "gate_volumes",
    }
    resume_node = gate_to_resume_node.get(current_gate, positioning_node)

    recovery: BootstrapState = {
        "run_id": run_id,
        "logline": logline,
        "premise": premise,
        "target_words": target_words,
        "positioning": positioning,
        "project_id": project_id,
        "ctx": ctx,
        "completed_steps": completed,
        "errors": [],
    }
    graph.update_state(config, recovery, as_node=resume_node)
    logger.warning(
        "Restored bootstrap checkpoint for run %s from DB "
        "(in-memory checkpointer was empty; gate=%s resume_node=%s)",
        run_id,
        current_gate,
        resume_node,
    )
    return True


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
    """emit start → svc.<fn_name> → emit done；失败则 interrupt 等待用户重试，不继续后续步骤。"""
    from app.services.bootstrap.step_failure import pause_for_step_retry, user_wants_step_retry
    from app.services.llm_errors import format_llm_error_message

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    from app.models import Project
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    while True:
        emit(run_id, "step_start", db, step=step, label=label)
        try:
            result = await asyncio.wait_for(
                getattr(svc, fn_name)(project, ctx, **fn_kwargs),
                timeout=300.0,
            )
        except asyncio.TimeoutError:
            msg = f"{step} 超时（5 分钟），请重试或检查模型线路"
        except Exception as exc:
            msg = format_llm_error_message(exc)
        else:
            count = len(result) if isinstance(result, list) else (1 if result else 0)
            emit(run_id, "step_done", db, step=step, count=count)
            return {"ctx": ctx, "completed_steps": [step]}

        user = await pause_for_step_retry(
            state, config, step=step, message=msg, ctx=ctx,
        )
        if user_wants_step_retry(user):
            continue
        return {"ctx": ctx, "errors": [{"step": step, "reason": msg}]}


# ──────────────────────────────────────────────────────
# 节点：positioning / gate / project（含特殊逻辑，保留在本文件）
# ──────────────────────────────────────────────────────

async def node_positioning(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0：立项会议。完成后置 status=awaiting_gate 并推送 gate_pending 给前端。

    失败时走 interrupt + pause_for_step_retry（与其他步骤一致），用户可选择重试；
    不再 raise，避免整个 run 永久变成 failed 且无法恢复。
    """
    from app.services.bootstrap.step_failure import pause_for_step_retry, user_wants_step_retry

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    ctx.update({"logline": state["logline"], "premise": state["premise"],
                "target_words": state["target_words"]})

    while True:
        emit(run_id, "step_start", db, step="positioning", label="召开立项会议（题材定位）...")
        positioning = await svc._gen_positioning(ctx)
        if positioning:
            break
        msg = "立项定位生成未通过 schema 校验（已重试 3 次），请更换模型或精简创意后重试"
        emit(run_id, "error", db, step="positioning", message=msg)
        user = await pause_for_step_retry(
            state, config, step="positioning", message=msg, ctx=ctx,
        )
        if user_wants_step_retry(user):
            continue
        return {"ctx": ctx, "errors": [{"step": "positioning", "reason": msg}]}

    ctx["positioning"] = positioning
    emit(run_id, "step_done", db, step="positioning", count=1,
         preview=(positioning.get("selling_point") or "")[:30])
    emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
         step="positioning", positioning=positioning,
         message="请确认或修改立项定位后点击「继续生成」")
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
    return {"positioning": positioning, "ctx": ctx, "completed_steps": ["positioning"]}


async def node_gate(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0 后闸门：确认 / 编辑 / 重新召开立项会议（regenerate）。"""
    from langgraph.types import interrupt

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
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
        ctx["positioning"] = updated
        emit(run_id, "gate_passed", db, persist_status="running",
             step="positioning", positioning=updated)
        return {"positioning": updated, "ctx": ctx}


async def node_project(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 1：生成项目基础信息并落库，回填 BootstrapRun.project_id。"""
    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
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
async def node_opening_contract(s, c=None): return await _run_step(s, c, "opening_contract", "规划开局追读承诺...", "_gen_opening_contract")   # noqa: E501
async def node_core_mysteries(s, c=None):   return await _run_step(s, c, "core_mysteries",   "预分配全书核心谜题...", "_gen_core_mysteries")    # noqa: E501
# node_emotion_arc / node_villain_arc / node_memory / node_relations 已合并为
# node_emotion_villain / node_memory_relations（见 graph_nodes.py）


# ──────────────────────────────────────────────────────
# 构建 StateGraph
# ──────────────────────────────────────────────────────

def _build_graph() -> StateGraph:
    from app.services.bootstrap.graph_nodes import (
        node_characters, node_skills_items, node_volumes,
        node_vol1_chapters, node_ch1_scenes, node_consistency,
        node_emotion_villain, node_memory_relations,
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
        ("emotion_villain",      node_emotion_villain),   # emotion_arc+villain_arc 并行
        ("memory_relations",     node_memory_relations),  # memory+relations 并行
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
        "volumes", "gate_volumes",
        "emotion_villain", "memory_relations", "core_mysteries",
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
    """后台任务：执行图至 gate interrupt 暂停；resume 由 resume_bootstrap() 继续。

    注意：当前使用进程内 MemorySaver 作为 checkpointer，重启进程后 checkpoint 清空。
    多 worker 部署（gunicorn -w N / uvicorn --workers N）时，resume 请求可能落到
    不同进程，导致 checkpoint miss，需切换为 PostgresSaver。
    """
    import os
    _worker_count = int(os.environ.get("WEB_CONCURRENCY", 1))
    if _worker_count > 1:
        logger.warning(
            "Bootstrap run %s: 检测到 WEB_CONCURRENCY=%d（多 worker），"
            "当前 MemorySaver 为进程内单例，resume 在跨 worker 时会 checkpoint miss；"
            "生产部署请切换 PostgresSaver（见 graph.py _checkpointer）",
            run_id,
            _worker_count,
        )
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
        if not run or run.status not in ("awaiting_gate", "awaiting_retry"):
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
        if run:
            restore_bootstrap_checkpoint_if_lost(
                bootstrap_graph, run_id=run_id, run=run, config=config,
            )
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
            elif run and run.status == "awaiting_retry":
                pass  # 保持 SSE，等待用户 retry_step
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
