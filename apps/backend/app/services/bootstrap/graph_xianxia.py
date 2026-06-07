"""graph_xianxia.py — 番茄·玄幻修仙直白线专属节点（mode=xianxia）。

拓扑与番茄线（graph_fanqie）几乎一致，**只替换战力/卷骨架主轴**为契约驱动：
  - power_systems 槽 → cultivation_contract（无条件境界轴 + 落库境界预算契约）
  - volumes 槽       → volumes_xianxia（契约硬执行 + 落库后确定性 clamp）
其余 positioning / 爽文公式 / 势力 / 人物 / 设定 / 节奏 / 承诺 / 双校验全部**复用**
番茄线节点函数（见 pipeline/styles 的 ``xianxia`` 配置），不复制番茄逻辑、不改番茄文件。

设计主张：把「第一卷修满」从 prompt 软约束 + 不阻断 warning，改为
「代码算定契约 → prompt 硬注入窗口 → 落库后确定性覆写」三道闸，结构性根治。
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
from app.services.bootstrap.graph_fanqie import _fanqie_step

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────
# Phase A：修仙原生立项（replaces 番茄 algo_positioning）
# ──────────────────────────────────────────────────────

async def node_xianxia_positioning(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0：修仙第一性原理立项，完成后置闸门等待确认。"""
    from app.services.bootstrap.steps.xianxia.positioning_xianxia import (
        gen_xianxia_positioning,
    )

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    emit(run_id, "step_start", db, step="positioning", label="召开修仙立项会议（子类型/爽感/张力）...")
    ctx = dict(state.get("ctx") or {})
    ctx.update({"logline": state["logline"], "premise": state["premise"],
                "target_words": state["target_words"]})
    xp = await gen_xianxia_positioning(svc, ctx)

    emit(run_id, "step_done", db, step="positioning", count=1,
         preview=f"{xp.get('subgenre', '')[:12]}·{xp.get('core_satisfaction', '')[:14]}")
    emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
         step="positioning", positioning=xp,
         message="请确认修仙子类型与核心爽感后点击「继续生成」")
    _persist(db, run_id, {}, gate_data={
        "kind": "positioning", "positioning": xp,
        "logline": state["logline"], "premise": state.get("premise") or "",
        "target_words": state.get("target_words"),
    })
    return {"positioning": xp, "ctx": ctx, "completed_steps": ["positioning"]}


async def node_xianxia_gate(state: BootstrapState, config: dict | None = None) -> dict:
    """Step 0 确认闸门：支持 approve / regenerate。"""
    from app.services.bootstrap.steps.xianxia.positioning_xianxia import (
        gen_xianxia_positioning,
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
            positioning = await gen_xianxia_positioning(svc, ctx)
            emit(run_id, "step_done", db, step="positioning", count=1,
                 preview=positioning.get("subgenre", "")[:20])
            emit(run_id, "gate_pending", db, persist_status="awaiting_gate",
                 step="positioning", positioning=positioning,
                 message="请再次确认修仙立项定位后继续生成")
            _persist(db, run_id, {}, gate_data={
                "kind": "positioning", "positioning": positioning,
                "logline": state["logline"], "premise": state.get("premise") or "",
                "target_words": state.get("target_words"),
            })
            continue
        updated = user_input.get("positioning", positioning)
        if not isinstance(updated, dict):
            updated = positioning
        ctx["xianxia_positioning"] = updated
        ctx["positioning"] = to_generic_positioning(updated)
        emit(run_id, "gate_passed", db, persist_status="running",
             step="positioning", positioning=updated)
        return {"positioning": updated, "ctx": ctx}


# ──────────────────────────────────────────────────────
# Phase B：修仙金手指（咬合境界轴，replaces 番茄 fanqie_formula）
# ──────────────────────────────────────────────────────

async def node_golden_finger_xianxia(s, c=None):
    """金手指设计，须在 cultivation_axis 之后（引用真实境界轴）。"""
    from app.services.bootstrap.steps.xianxia.golden_finger_xianxia import (
        gen_golden_finger_xianxia,
    )

    return await _fanqie_step(
        s, c, "golden_finger", "设计修仙金手指（咬合境界轴 + 代价 + 进化）...",
        gen_golden_finger_xianxia,
    )


# ──────────────────────────────────────────────────────
# Phase C：修仙世界设定（replaces 通用 settings）
# ──────────────────────────────────────────────────────

async def node_world_xianxia(s, c=None):
    """修仙世界设定卡（灵气/突破代价/资源/秘境/妖兽/上古秘辛）。"""
    from app.services.bootstrap.steps.xianxia.world_xianxia import gen_world_xianxia

    return await _fanqie_step(
        s, c, "settings", "生成修仙世界设定卡（灵气·资源·宗门·秘境）...",
        gen_world_xianxia,
    )


async def node_factions_antagonist_xianxia(s, c=None):
    """合并节点：势力体系 + 卷级对立面 roster 一次 LLM 生成。

    replaces 通用 factions；并经 StyleConfig.skip_core 吞并 antagonist_ladder
    （-1 次 LLM 调用）。Boss 与势力同响应共生，结构上消除 Boss 挂靠不存在势力的冲突。
    """
    from app.services.bootstrap.steps.xianxia.factions_antagonist_xianxia import (
        gen_factions_antagonist_xianxia,
    )

    return await _fanqie_step(
        s, c, "factions", "生成势力体系 + 卷级对立面（合并·Boss挂靠真实势力）...",
        gen_factions_antagonist_xianxia,
    )


async def node_promise_seeds_xianxia(s, c=None):
    """合并节点：核心谜题 + 开局追读承诺一次 LLM 生成。

    replaces 通用 core_mysteries；并经 StyleConfig.skip_core 吞并 opening_contract
    （-1 次 LLM 调用）。复用 CORE 通用 schema，保住「无事实承诺」+ OC-LADDER 约束。
    """
    from app.services.bootstrap.steps.xianxia.promise_seeds_xianxia import (
        gen_promise_seeds_xianxia,
    )

    return await _fanqie_step(
        s, c, "promise_seeds", "预置核心谜题 + 开局追读承诺（合并）...",
        gen_promise_seeds_xianxia,
    )


async def node_cultivation_contract(state: BootstrapState, config: dict | None = None) -> dict:
    """境界主轴 + 境界预算契约（replaces power_systems）。"""
    from app.services.bootstrap.steps.xianxia.cultivation_contract import (
        gen_cultivation_contract,
    )

    return await _fanqie_step(
        state, config,
        "power_ladder", "构建修仙境界主轴 + 境界预算契约...",
        gen_cultivation_contract,
    )


async def node_volumes_xianxia(state: BootstrapState, config: dict | None = None) -> dict:
    """契约执行式卷骨架（replaces volumes）；失败时 interrupt 暂停等待重试。"""
    from app.services.bootstrap.steps.xianxia.volumes_xianxia import gen_volumes_xianxia
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
    project = db.query(Project).filter(Project.id == state.get("project_id")).first()

    while True:
        emit(run_id, "step_start", db, step="volumes", label="规划卷骨架（境界预算契约硬执行）...")
        try:
            nodes = await asyncio.wait_for(
                gen_volumes_xianxia(svc, project, ctx), timeout=300.0,
            )
        except asyncio.TimeoutError:
            msg = "卷级结构生成超时（5 分钟），请重试"
        except Exception as exc:
            msg = f"卷级结构生成失败：{format_llm_error_message(exc)}"
            logger.warning("xianxia.volumes 失败 project=%s: %s", state.get("project_id"), exc)
        else:
            if nodes:
                ctx["_volume_ids"] = [str(n.id) for n in nodes]
                emit(run_id, "step_done", db, step="volumes", count=len(nodes),
                     preview=f"共{len(nodes)}卷（境界已锁契约）")
                return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": ["volumes"]}
            msg = "卷级结构生成结果为空，请重试或更换模型线路"

        user = await pause_for_step_retry(state, config, step="volumes", message=msg, ctx=ctx)
        if user_wants_step_retry(user):
            continue
        return {"ctx": sanitize_bootstrap_ctx(ctx), "errors": [{"step": "volumes", "reason": msg}]}
