"""
graph_runner.py — Bootstrap 后台任务入口（run / resume）

委托 pipeline.runner 执行；保留本模块路径以兼容既有 import。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def run_bootstrap(
    run_id: str, *, logline: str, premise: str, target_words: int,
    model_profile: str, llm_provider_id, user_id,
    writing_style: str = "standard",
) -> None:
    from app.services.bootstrap.graph import get_bootstrap_graph
    from app.services.bootstrap.pipeline.runner import run_pipeline
    from app.services.bootstrap.pipeline.styles import STYLE_REGISTRY

    await run_pipeline(
        get_bootstrap_graph(),
        STYLE_REGISTRY["sequential"],
        run_id,
        logline=logline,
        premise=premise,
        target_words=target_words,
        model_profile=model_profile,
        llm_provider_id=llm_provider_id,
        user_id=user_id,
        writing_style=writing_style,
    )


async def resume_bootstrap(
    run_id: str,
    resume_payload: dict,
    *,
    model_profile: str,
    llm_provider_id,
    user_id,
) -> None:
    from app.services.bootstrap.graph import get_bootstrap_graph
    from app.services.bootstrap.pipeline.runner import resume_pipeline

    await resume_pipeline(
        get_bootstrap_graph(),
        run_id,
        resume_payload,
        model_profile=model_profile,
        llm_provider_id=llm_provider_id,
        user_id=user_id,
    )


def _handle_run_error(db, run_id: str, exc: Exception) -> None:
    """更新 DB 状态为 failed 并推送 error 事件。"""
    from app.services.bootstrap.graph_sse import emit

    try:
        from app.models.bootstrap_run import BootstrapRun

        run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
        if run:
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            db.commit()
        emit(run_id, "error", message=str(exc))
    except Exception:
        pass
