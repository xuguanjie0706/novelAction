"""Bootstrap 自动模式：仅自动通过人工闸门，步骤失败不自动重试。

``gate_data.auto_mode=true`` 时仅在 ``awaiting_gate`` 链式 ``approve``（跳过闸门 UI）。
``awaiting_retry`` 不自动 ``retry_step``，由用户在创作端点「重试此步骤」。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Awaitable
from uuid import UUID

from app.database import SessionLocal
from app.models.bootstrap_run import BootstrapRun
from app.schemas.bootstrap_dabai_positioning import try_validate_dabai_positioning
from app.schemas.bootstrap_fanqie_positioning import try_validate_fanqie_positioning
from app.schemas.bootstrap_positioning import try_validate_positioning

logger = logging.getLogger(__name__)

_AUTO_RESUME_TASKS: dict[str, asyncio.Task] = {}
_RESUME_LOCKS: dict[str, asyncio.Lock] = {}
_MAX_AUTO_RESUME_ROUNDS = 24


def resume_lock(run_id: str) -> asyncio.Lock:
    """同一 run 同时只允许一个 resume/ainvoke，避免自动链与 HTTP 并发打穿 checkpoint。"""
    if run_id not in _RESUME_LOCKS:
        _RESUME_LOCKS[run_id] = asyncio.Lock()
    return _RESUME_LOCKS[run_id]


def is_auto_mode(gate_data: Any) -> bool:
    """是否启用自动模式（存于 BootstrapRun.gate_data）。"""
    return bool(isinstance(gate_data, dict) and gate_data.get("auto_mode"))


def merge_gate_data_with_auto_mode(
    gate_data: dict | None,
    auto_mode: bool,
    *,
    llm_provider_id: Any = None,
) -> dict:
    """创建 run 时写入 gate_data 根字段（含后续链式 resume 所需的 provider）。"""
    base = dict(gate_data) if isinstance(gate_data, dict) else {}
    if auto_mode:
        base["auto_mode"] = True
    else:
        base.pop("auto_mode", None)
    if llm_provider_id is not None:
        base["llm_provider_id"] = str(llm_provider_id)
    return base


def _llm_provider_from_gate_data(gd: dict) -> Any:
    raw = gd.get("llm_provider_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def merge_gate_data_snapshot(existing: Any, update: dict) -> dict:
    """合并闸门快照，保留 ``auto_mode``（各步 _persist 不得整表覆盖创建时的标志）。"""
    base = dict(existing) if isinstance(existing, dict) else {}
    merged = {**base, **update}
    if base.get("auto_mode"):
        merged["auto_mode"] = True
    return merged


def build_auto_resume_payload(run: BootstrapRun) -> dict | None:
    """根据 run 状态构造 LangGraph Command(resume=...) 载荷；无法自动时返回 None。"""
    gd = run.gate_data if isinstance(run.gate_data, dict) else {}

    if run.status == "awaiting_retry" or gd.get("kind") == "step_retry":
        return None

    if run.status != "awaiting_gate":
        return None

    kind = gd.get("kind") or "positioning"
    if kind == "positioning":
        raw = gd.get("positioning")
        if not isinstance(raw, dict) or not raw:
            logger.warning("auto_mode: run %s 缺少 positioning，无法自动 resume", run.id)
            return None
        if run.mode == "fanqie":
            normalized, err = try_validate_fanqie_positioning(raw)
        elif run.mode == "dabai":
            benchmark = gd.get("benchmark") if isinstance(gd.get("benchmark"), dict) else None
            normalized, err = try_validate_dabai_positioning(raw, benchmark=benchmark)
        else:
            normalized, err = try_validate_positioning(raw)
        if err or normalized is None:
            logger.warning("auto_mode: positioning 校验失败 run=%s: %s", run.id, err)
            return None
        return {"action": "approve", "positioning": normalized}

    return {"action": "approve"}


def schedule_auto_resume_for_run(run_id: str) -> None:
    """从 DB 读取 run 并排队自动 resume（供 _persist / run 结束等统一入口）。"""
    db = SessionLocal()
    try:
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if not run:
            return
        gd = run.gate_data if isinstance(run.gate_data, dict) else {}
        from app.services.bootstrap.graph import get_graph_for_mode
        from app.services.bootstrap.pipeline.runner import resume_pipeline

        mode = run.mode or "sequential"
        graph = get_graph_for_mode(mode)

        async def resume_fn(
            rid: str, payload: dict, *, model_profile: str, llm_provider_id, user_id,
        ) -> None:
            await resume_pipeline(
                graph, rid, payload,
                model_profile=model_profile,
                llm_provider_id=llm_provider_id,
                user_id=user_id,
            )

        schedule_auto_resume_if_needed(
            str(run.id),
            mode=mode,
            model_profile=run.model_profile or "gemini",
            llm_provider_id=_llm_provider_from_gate_data(gd),
            user_id=run.user_id,
            resume_fn=resume_fn,
        )
    finally:
        db.close()


def schedule_auto_resume_if_needed(
    run_id: str,
    *,
    mode: str,
    model_profile: str,
    llm_provider_id: Any,
    user_id: Any,
    resume_fn: Callable[..., Awaitable[None]],
) -> None:
    """若 run 为自动模式且停在闸门，排队后台链式 approve（不处理 awaiting_retry）。"""
    db = SessionLocal()
    try:
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if not run or not is_auto_mode(run.gate_data):
            return
        if run.status != "awaiting_gate":
            return
        if build_auto_resume_payload(run) is None:
            return
    finally:
        db.close()

    existing = _AUTO_RESUME_TASKS.get(run_id)
    if existing and not existing.done():
        return

    task = asyncio.create_task(
        _auto_resume_chain(
            run_id,
            mode=mode,
            model_profile=model_profile,
            llm_provider_id=llm_provider_id,
            user_id=user_id,
            resume_fn=resume_fn,
        ),
        name=f"bootstrap-auto-{run_id[:8]}",
    )
    _AUTO_RESUME_TASKS[run_id] = task

    def _cleanup(t: asyncio.Task) -> None:
        if _AUTO_RESUME_TASKS.get(run_id) is t:
            _AUTO_RESUME_TASKS.pop(run_id, None)

    task.add_done_callback(_cleanup)


async def _auto_resume_chain(
    run_id: str,
    *,
    mode: str,
    model_profile: str,
    llm_provider_id: Any,
    user_id: Any,
    resume_fn: Callable[..., Awaitable[None]],
) -> None:
    """循环 resume 直至非暂停态或达到轮次上限。"""
    await asyncio.sleep(0.12)

    for round_i in range(_MAX_AUTO_RESUME_ROUNDS):
        db = SessionLocal()
        try:
            run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
            if not run or not is_auto_mode(run.gate_data):
                return
            if run.status in ("done", "failed", "cancelled"):
                return
            payload = build_auto_resume_payload(run)
            if not payload:
                if run.status == "running":
                    events = run.events if isinstance(run.events, list) else []
                    if events and events[-1].get("event") == "step_done":
                        last_step = str(events[-1].get("step") or "")
                        if last_step in ("consistency", "canon_audit"):
                            logger.info(
                                "auto_mode: run %s 图已跑完但未落 done，停止空转（step=%s）",
                                run_id, last_step,
                            )
                            return
                    if round_i >= 3:
                        logger.info(
                            "auto_mode: run %s status=running 无闸门可 resume，停止空转 round=%s",
                            run_id, round_i,
                        )
                        return
                    await asyncio.sleep(0.35)
                    continue
                logger.info(
                    "auto_mode: run %s 停止自动 resume（status=%s round=%s）",
                    run_id,
                    run.status,
                    round_i,
                )
                return
            mp = model_profile or run.model_profile or "gemini"
            gd = run.gate_data if isinstance(run.gate_data, dict) else {}
            lip = llm_provider_id if llm_provider_id is not None else _llm_provider_from_gate_data(gd)
        finally:
            db.close()

        logger.info(
            "auto_mode: run %s 自动 resume round=%s action=%s",
            run_id,
            round_i,
            payload.get("action"),
        )
        try:
            await resume_fn(
                run_id,
                payload,
                model_profile=mp,
                llm_provider_id=lip,
                user_id=user_id,
            )
        except Exception:
            logger.exception("auto_mode: resume 失败 run=%s", run_id)
            return

        run = await _wait_run_after_resume(run_id)
        if not run:
            await asyncio.sleep(0.35)
            continue
        if not is_auto_mode(run.gate_data):
            return
        if run.status in ("done", "failed", "cancelled"):
            return

        await asyncio.sleep(0.12)

    logger.warning("auto_mode: run %s 达到最大自动 resume 轮次 %s", run_id, _MAX_AUTO_RESUME_ROUNDS)


async def _wait_run_after_resume(
    run_id: str,
    *,
    timeout_sec: float = 45.0,
) -> BootstrapRun | None:
    """resume 返回后等待 DB 落到 awaiting_gate / 终态（避免 status=running 时链式任务误退出）。"""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        db = SessionLocal()
        try:
            run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
            if not run:
                return None
            if run.status in (
                "awaiting_gate",
                "awaiting_retry",
                "done",
                "failed",
                "cancelled",
            ):
                return run
        finally:
            db.close()
        await asyncio.sleep(0.2)
    return None
