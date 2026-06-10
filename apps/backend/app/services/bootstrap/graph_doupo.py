"""graph_doupo.py — 斗破式大白文玄幻线（mode=doupo）专属 LangGraph 节点。

设计主张
--------
doupo **完全基于通用（sequential）线**，不复制、不依赖番茄（fanqie）任何代码。
拓扑＝通用 CORE + 三个题材语义替换节点 + 一个合并节点 + 通用四道闸门：
  - positioning 槽 → positioning_doupo（斗气大陆纯爽文立项，禁修仙、禁上帝视角）
  - power_systems 槽 → power_axis_doupo（单条斗气主轴，绕开修仙多轴架构师）
  - factions 槽 → factions_antagonist_doupo（势力 + 卷级对立面 一次 LLM，吞 antagonist_ladder）
  - settings 槽 → world_doupo（精简斗气大陆世界卡）
  - 功法/法宝：复用通用 CORE skills_items（人物**后**生成，精确挂人物 UUID + 按境界择人）
另对共享 volumes 步骤挂 build_doupo_volumes_block（大纲质量增强 + 斗气进度预算）。

本文件自带 ``_doupo_step`` 薄执行器（拷贝自通用模式，零 fanqie 引用），其余复用
``graph`` 模块的 _make_svc / _persist / _resolve_config / _state_run_id / emit。
红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any

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
from app.services.bootstrap.json_once import BootstrapStepError

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────
# 通用薄步骤执行器（Doupo 版，零 fanqie 引用）
# ──────────────────────────────────────────────────────

def _step_result_ok(result) -> tuple[bool, int]:
    """判断步骤产物是否有效；返回 (是否成功, 用于 step_done 的 count)。"""
    if isinstance(result, list):
        return len(result) > 0, len(result)
    return bool(result), (1 if result else 0)


async def _doupo_step(
    state: BootstrapState,
    config: dict | None,
    step: str,
    label: str,
    fn,
    *,
    needs_project: bool = True,
) -> dict:
    """emit start → fn → emit done；失败则 interrupt 等待用户 retry_step（与通用/同人线一致）。"""
    from app.services.bootstrap.step_failure import (
        pause_for_step_retry,
        user_wants_step_retry,
    )
    from app.services.llm_errors import format_llm_error_message

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    ctx = dict(state.get("ctx") or {})
    project = None
    if needs_project:
        project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    async def _invoke_step() -> Any:
        if inspect.iscoroutinefunction(fn):
            if needs_project:
                return await fn(svc, project, ctx)
            return await fn(svc, ctx)
        if needs_project:
            return await asyncio.to_thread(fn, svc, project, ctx)
        return await asyncio.to_thread(fn, svc, ctx)

    while True:
        emit(run_id, "step_start", db, step=step, label=label)
        try:
            result = await asyncio.wait_for(_invoke_step(), timeout=300.0)
        except BootstrapStepError as exc:
            msg = str(exc)
        except asyncio.TimeoutError:
            msg = f"{step} 超时（5 分钟），请重试或检查模型线路"
        except Exception as exc:  # noqa: BLE001
            msg = f"{step} 失败：{format_llm_error_message(exc)}"
            logger.warning("doupo step %s failed: %s", step, exc)
        else:
            ok, count = _step_result_ok(result)
            if ok:
                emit(run_id, "step_done", db, step=step, count=count)
                return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": [step]}
            msg = f"{step} 生成结果为空，请重试或更换模型线路"

        user = await pause_for_step_retry(state, config, step=step, message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": sanitize_bootstrap_ctx(ctx), "errors": [{"step": step, "reason": msg}]}


# ──────────────────────────────────────────────────────
# Step 0：斗破式立项 + 确认闸门
# ──────────────────────────────────────────────────────

async def node_doupo_positioning(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0：斗气大陆纯爽文立项，完成后置闸门等待确认。"""
    from app.services.bootstrap.steps.doupo.positioning_doupo import gen_doupo_positioning

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="positioning",
         label="召开斗破式立项会议（子类型/核心爽感/金手指）...")
    ctx = dict(state.get("ctx") or {})
    ctx.update({"logline": state["logline"], "premise": state["premise"],
                "target_words": state["target_words"]})
    dp = await gen_doupo_positioning(svc, ctx)

    emit(run_id, "step_done", db, step="positioning", count=1,
         preview=f"{dp.get('subgenre', '')[:12]}·{dp.get('core_satisfaction', '')[:14]}")
    emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
         step="positioning", positioning=dp,
         message="请确认斗气大陆子类型与核心爽感后点击「继续生成」")
    _persist(db, run_id, {}, gate_data={
        "kind": "positioning", "positioning": dp,
        "logline": state["logline"], "premise": state.get("premise") or "",
        "target_words": state.get("target_words"),
    })
    return {"positioning": dp, "ctx": ctx, "completed_steps": ["positioning"]}


async def node_doupo_gate(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0 确认闸门：支持 approve / regenerate。"""
    from app.services.bootstrap.steps.doupo.positioning_doupo import (
        gen_doupo_positioning,
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
            positioning = await gen_doupo_positioning(svc, ctx)
            emit(run_id, "step_done", db, step="positioning", count=1,
                 preview=positioning.get("subgenre", "")[:20])
            emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
                 step="positioning", positioning=positioning,
                 message="请再次确认斗破立项定位后继续生成")
            _persist(db, run_id, {}, gate_data={
                "kind": "positioning", "positioning": positioning,
                "logline": state["logline"], "premise": state.get("premise") or "",
                "target_words": state.get("target_words"),
            })
            continue
        updated = user_input.get("positioning", positioning)
        if not isinstance(updated, dict):
            updated = positioning
        ctx["doupo_positioning"] = updated
        ctx["positioning"] = to_generic_positioning(updated)
        emit(run_id, "gate_passed", db, persist_status="running",
             step="positioning", positioning=updated)
        return {"positioning": updated, "ctx": ctx}


# ──────────────────────────────────────────────────────
# Step 2 / 3+6+7 / 8：题材语义替换节点（薄壳）
# ──────────────────────────────────────────────────────

async def node_doupo_power_axis(s, c=None):
    """单条斗气主轴（replaces 通用 power_systems 修仙多轴）。"""
    from app.services.bootstrap.steps.doupo.power_axis_doupo import gen_doupo_power_axis

    return await _doupo_step(
        s, c, "power_systems", "构建斗气阶位主轴（斗者→斗帝，单主轴直白）...",
        gen_doupo_power_axis,
    )


async def node_doupo_factions_antagonist(s, c=None):
    """合并节点：势力 + 卷级对立面 一次 LLM（replaces factions，吞 antagonist_ladder）。

    放在人物**前**（势力/Boss 是人物建档的依赖）；功法/法宝改由通用 CORE skills_items
    在人物**后**生成，以精确挂人物 UUID。
    """
    from app.services.bootstrap.steps.doupo.factions_antagonist_doupo import (
        gen_factions_antagonist_doupo,
    )

    return await _doupo_step(
        s, c, "factions", "生成势力 + 卷级对立面（合并·Boss挂靠真实势力）...",
        gen_factions_antagonist_doupo,
    )


async def node_doupo_world(s, c=None):
    """精简斗气大陆世界设定卡（replaces 通用 settings）。"""
    from app.services.bootstrap.steps.doupo.world_doupo import gen_world_doupo

    return await _doupo_step(
        s, c, "settings", "生成斗气大陆世界设定卡（精简6张·白话直给）...",
        gen_world_doupo,
    )
