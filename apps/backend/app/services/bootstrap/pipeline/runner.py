"""统一 Bootstrap 后台任务入口（run / resume）。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from langgraph.types import Command

from app.database import SessionLocal
from app.models.bootstrap_run import BootstrapRun
from app.services.bootstrap.graph_sse import emit, push
from app.services.bootstrap.pipeline.builder import get_graph_hooks
from app.services.bootstrap.pipeline.hook_context import reset_active_hooks, set_active_hooks
from app.services.bootstrap.pipeline.node_spec import StyleConfig

logger = logging.getLogger(__name__)


def _normalize_writing_style(style: str, config: StyleConfig) -> str:
    ws = str(style or "").strip().lower()
    if ws not in ("plain", "standard", "dense"):
        ws = config.default_writing_style
    return ws


def _build_initial_state(
    run_id: str,
    *,
    logline: str,
    premise: str,
    target_words: int,
    writing_style: str,
    config: StyleConfig,
    extra_ctx: dict | None = None,
) -> dict:
    ctx: dict[str, Any] = {"writing_style": _normalize_writing_style(writing_style, config)}
    if extra_ctx:
        ctx.update(extra_ctx)
    return {
        "run_id": run_id,
        "logline": logline,
        "premise": premise,
        "target_words": target_words,
        "positioning": {},
        "project_id": None,
        "ctx": ctx,
        "completed_steps": [],
        "errors": [],
    }


async def run_pipeline(
    graph: Any,
    style: StyleConfig,
    run_id: str,
    *,
    logline: str,
    premise: str,
    target_words: int,
    model_profile: str,
    llm_provider_id,
    user_id,
    writing_style: str | None = None,
    extra_ctx: dict | None = None,
) -> None:
    """首次启动图执行；在 gate interrupt 或完成时返回。"""
    from app.services.bootstrap.graph_runner import _handle_run_error

    db = SessionLocal()
    token = set_active_hooks(get_graph_hooks(graph))
    try:
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if run:
            run.status = "running"
            db.commit()
        initial = _build_initial_state(
            run_id,
            logline=logline,
            premise=premise,
            target_words=target_words,
            writing_style=writing_style or style.default_writing_style,
            config=style,
            extra_ctx=extra_ctx,
        )
        cfg = {
            "configurable": {
                "thread_id": run_id,
                "db": db,
                "model_profile": model_profile,
                "llm_provider_id": llm_provider_id,
                "user_id": user_id,
            },
        }
        await graph.ainvoke(initial, config=cfg)
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if not run or run.status not in ("awaiting_gate", "awaiting_retry"):
            push(run_id, {"event": "__stream_end__"})
        else:
            from app.services.bootstrap.gate_auto import schedule_auto_resume_for_run
            schedule_auto_resume_for_run(run_id)
    except asyncio.CancelledError:
        emit(run_id, "cancelled", db, persist_status="cancelled", message="用户已取消生成")
        push(run_id, {"event": "__stream_end__"})
        raise
    except Exception as exc:
        logger.exception("Bootstrap run %s failed (style=%s)", run_id, style.style_id)
        _handle_run_error(db, run_id, exc)
        push(run_id, {"event": "__stream_end__"})
    finally:
        reset_active_hooks(token)
        db.close()


async def resume_pipeline(
    graph: Any,
    run_id: str,
    resume_payload: dict,
    *,
    model_profile: str,
    llm_provider_id,
    user_id,
    recovered_from_failed: bool = False,
) -> None:
    """从 checkpoint 继续执行。"""
    from app.services.bootstrap.gate_auto import resume_lock
    from app.services.bootstrap.graph_runner import _handle_run_error

    async with resume_lock(run_id):
        db = SessionLocal()
        token = set_active_hooks(get_graph_hooks(graph))
        try:
            run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
            if run:
                run.status = "running"
                db.commit()
            cfg = {
                "configurable": {
                    "thread_id": run_id,
                    "db": db,
                    "model_profile": model_profile,
                    "llm_provider_id": llm_provider_id,
                    "user_id": user_id,
                },
            }
            if recovered_from_failed:
                # 异常中断且无 interrupt 时，从 PG checkpoint 续跑失败节点
                await graph.ainvoke(None, config=cfg)
            else:
                await graph.ainvoke(Command(resume=dict(resume_payload)), config=cfg)
        except asyncio.CancelledError:
            emit(run_id, "cancelled", db, persist_status="cancelled", message="用户已取消生成")
            raise
        except Exception as exc:
            logger.exception("Bootstrap resume %s failed", run_id)
            _handle_run_error(db, run_id, exc)
        finally:
            try:
                run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
                if run and run.status in ("done", "failed", "cancelled"):
                    push(run_id, {"event": "__stream_end__"})
                elif run and run.status == "awaiting_gate":
                    from app.services.bootstrap.gate_auto import schedule_auto_resume_for_run
                    schedule_auto_resume_for_run(run_id)
            except Exception:
                pass
            reset_active_hooks(token)
            db.close()
