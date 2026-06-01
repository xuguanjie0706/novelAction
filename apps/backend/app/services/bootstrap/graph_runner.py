"""
graph_runner.py — Bootstrap 后台任务入口（run / resume）

职责：
- run_bootstrap: 首次启动图执行至 gate interrupt 暂停
- resume_bootstrap: 从 AsyncPostgresSaver checkpoint 继续（checkpoint 持久化到 PG，重启安全）
- _handle_run_error: 更新 DB 状态为 failed

不含图定义、节点函数或 SSE 注册表（见 graph.py / graph_sse.py）。
"""
from __future__ import annotations

import asyncio
import logging

from app.database import SessionLocal
from app.models.bootstrap_run import BootstrapRun

from app.services.bootstrap.graph_sse import emit, push

logger = logging.getLogger(__name__)


async def run_bootstrap(
    run_id: str, *, logline: str, premise: str, target_words: int,
    model_profile: str, llm_provider_id, user_id,
) -> None:
    """后台任务：执行图至 gate interrupt 暂停；resume 由 resume_bootstrap() 继续。

    Checkpoint 由 AsyncPostgresSaver 持久化到 PostgreSQL，重启 / 多 worker 均安全。
    """
    from app.services.bootstrap.graph import get_bootstrap_graph, BootstrapState
    bootstrap_graph = get_bootstrap_graph()
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
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if not run or run.status != "awaiting_gate":
            push(run_id, {"event": "__stream_end__"})
        else:
            from app.services.bootstrap.gate_auto import schedule_auto_resume_for_run
            schedule_auto_resume_for_run(run_id)
    except asyncio.CancelledError:
        emit(run_id, "cancelled", db, persist_status="cancelled", message="用户已取消生成")
        push(run_id, {"event": "__stream_end__"})
        raise
    except Exception as exc:
        logger.exception("Bootstrap run %s failed", run_id)
        _handle_run_error(db, run_id, exc)
        push(run_id, {"event": "__stream_end__"})
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
    """从 AsyncPostgresSaver checkpoint 继续，以 Command(resume=...) 传入用户决策。"""
    from app.services.bootstrap.gate_auto import resume_lock

    async with resume_lock(run_id):
        await _resume_bootstrap_impl(
            run_id, resume_payload,
            model_profile=model_profile,
            llm_provider_id=llm_provider_id,
            user_id=user_id,
        )


async def _resume_bootstrap_impl(
    run_id: str, resume_payload: dict, *,
    model_profile: str, llm_provider_id, user_id,
) -> None:
    from langgraph.types import Command
    from app.services.bootstrap.graph import get_bootstrap_graph
    bootstrap_graph = get_bootstrap_graph()

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
        # AsyncPostgresSaver 持久化到 PG，无需手动 restore checkpoint
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
        try:
            run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
            if run and run.status in ("done", "failed", "cancelled"):
                push(run_id, {"event": "__stream_end__"})
            elif run and run.status == "awaiting_gate":
                from app.services.bootstrap.gate_auto import schedule_auto_resume_for_run
                schedule_auto_resume_for_run(run_id)
        except Exception:
            pass
        db.close()


def _handle_run_error(db, run_id: str, exc: Exception) -> None:
    """更新 DB 状态为 failed 并推送 error 事件。"""
    try:
        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if run:
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            db.commit()
        emit(run_id, "error", message=str(exc))
    except Exception:
        pass
