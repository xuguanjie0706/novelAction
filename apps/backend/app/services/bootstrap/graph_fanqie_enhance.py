"""
番茄增强节点 — 插入标准串行步进管线的条件节点。

当 positioning.pace_type == "fast" 时执行番茄专属步骤，否则静默跳过。
产物写入 Project.extra（与 graph_fanqie.py 独立管线相同的 step 函数），
下游 context_vol_expand / vol_chapter_plans 根据这些 extra 字段做番茄适配。

插入位置：
  project → [fanqie_contrast → fanqie_golden_finger → fanqie_face_slap] → power_systems
  emotion_villain → [fanqie_rhythm → fanqie_audit] → memory_relations
"""
from __future__ import annotations

import asyncio
import logging

from app.services.bootstrap.graph import (
    BootstrapState,
    _make_svc,
    _resolve_config,
    _state_run_id,
    emit,
)
from app.services.bootstrap.graph_ctx import sanitize_bootstrap_ctx

logger = logging.getLogger(__name__)


def _is_fanqie(state: BootstrapState) -> bool:
    """检测当前 Bootstrap 是否为番茄模式（pace_type == "fast"）。"""
    pos = (state.get("positioning") or {})
    if pos.get("pace_type") == "fast":
        return True
    ctx = state.get("ctx") or {}
    ctx_pos = ctx.get("positioning") or {}
    return ctx_pos.get("pace_type") == "fast"


async def _fanqie_enhance_step(
    state: BootstrapState,
    config: dict | None,
    step: str,
    label: str,
    fn,
) -> dict:
    """番茄增强步骤通用执行器：pace_type != fast 时跳过。"""
    if not _is_fanqie(state):
        return {"completed_steps": []}

    config = _resolve_config(config)
    db = config["configurable"]["db"]
    run_id = _state_run_id(state, config)
    svc = _make_svc(config)
    ctx = sanitize_bootstrap_ctx(dict(state.get("ctx") or {}))

    from app.models import Project
    project = db.query(Project).filter(
        Project.id == state.get("project_id"),
    ).first()

    emit(run_id, "step_start", db, step=step, label=label)
    try:
        result = await asyncio.wait_for(fn(svc, project, ctx), timeout=300.0)
    except asyncio.TimeoutError:
        emit(run_id, "error", db, step=step, message=f"{step} 超时，已跳过")
        return {
            "ctx": sanitize_bootstrap_ctx(ctx),
            "completed_steps": [step],
            "errors": [{"step": step, "reason": "timeout"}],
        }
    except Exception as exc:
        logger.warning("fanqie enhance %s failed: %s", step, exc)
        emit(run_id, "error", db, step=step, message=f"{step} 失败：{exc}")
        return {
            "ctx": sanitize_bootstrap_ctx(ctx),
            "completed_steps": [step],
            "errors": [{"step": step, "reason": str(exc)}],
        }

    count = len(result) if isinstance(result, list) else (1 if result else 0)
    emit(run_id, "step_done", db, step=step, count=count)
    return {"ctx": sanitize_bootstrap_ctx(ctx), "completed_steps": [step]}


# ── 节点函数 ──────────────────────────────────────────────


async def node_fanqie_contrast(
    state: BootstrapState, config: dict | None = None,
) -> dict:
    """番茄增强：落差工程（初始耻辱状态 + 触发事件设计）。"""
    from app.services.bootstrap.steps.fanqie.contrast_design import (
        gen_contrast_design,
    )
    return await _fanqie_enhance_step(
        state, config, "fanqie_contrast",
        "设计主角落差（越惨越爽）...", gen_contrast_design,
    )


async def node_fanqie_golden_finger(
    state: BootstrapState, config: dict | None = None,
) -> dict:
    """番茄增强：金手指工程（类型/可视化/5阶段成长路线图）。"""
    from app.services.bootstrap.steps.fanqie.golden_finger import (
        gen_golden_finger,
    )
    return await _fanqie_enhance_step(
        state, config, "fanqie_golden_finger",
        "设计金手指工程...", gen_golden_finger,
    )


async def node_fanqie_face_slap(
    state: BootstrapState, config: dict | None = None,
) -> dict:
    """番茄增强：打脸地图（对象谱系 + 首次打脸 + 类型多样性）。"""
    from app.services.bootstrap.steps.fanqie.face_slap_map import (
        gen_face_slap_map,
    )
    return await _fanqie_enhance_step(
        state, config, "fanqie_face_slap",
        "规划打脸地图...", gen_face_slap_map,
    )


async def node_fanqie_rhythm(
    state: BootstrapState, config: dict | None = None,
) -> dict:
    """番茄增强：爽点节奏图 + 剧情储量池（50章标签 + 干旱检测）。"""
    from app.services.bootstrap.steps.fanqie.rhythm_map import (
        gen_rhythm_map,
    )
    return await _fanqie_enhance_step(
        state, config, "fanqie_rhythm",
        "生成爽点节奏图...", gen_rhythm_map,
    )


async def node_fanqie_audit(
    state: BootstrapState, config: dict | None = None,
) -> dict:
    """番茄增强：算法双校验（类型信号 + 爽感密度审计）。"""
    from app.services.bootstrap.steps.fanqie.signal_audit import (
        gen_signal_audit,
    )
    return await _fanqie_enhance_step(
        state, config, "fanqie_audit",
        "执行番茄算法双校验...", gen_signal_audit,
    )
