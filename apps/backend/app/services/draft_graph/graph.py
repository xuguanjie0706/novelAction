"""
draft_graph/graph.py — chapter_draft_graph StateGraph 定义与执行入口。

拓扑：
  START
    → load_context
    → scene_planning
    → human_review_blueprint   ←─── interrupt（skip_blueprint_review=False 时）
        ┌─ approve ──────────────────┐
        ├─ rewrite → scene_planning ─┘  (loop back)
        └─ skip ──────────────────────→ END

    → draft_scenes
    → quality_check
    → [score >= threshold?]
        ├─ yes → debrief → save_commit → END
        └─ no  → human_review_quality  ←─── interrupt（skip_quality_review=False 时）
                    ├─ accept     → debrief → save_commit → END
                    ├─ auto_fix   → auto_revision → quality_check (loop, max_iterations)
                    └─ rewrite    → scene_planning (full rewrite loop)

Checkpointing：MemorySaver（进程内；thread_id = job_id）。
  - 前端断线：后台任务继续运行，不受影响
  - 服务器重启：MemorySaver 丢失；Worker 在启动时把 running 状态 job 标为 failed，
    提示用户重新提交（比当前 SSE 断线丢失已有巨大改善）
  - 未来升级 PostgresSaver 只需换 _checkpointer，图拓扑和节点无需修改

代码红线：本文件 ≤ 400 行。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.services.draft_graph.events import (
    emit,
    send_sentinel,
    subscribe,
    unsubscribe,
    update_job,
)
from app.services.draft_graph.nodes import (
    auto_revision,
    debrief,
    draft_scenes,
    human_review_blueprint,
    human_review_quality,
    load_context,
    quality_check,
    save_commit,
    scene_planning,
)
from app.services.draft_graph.state import ChapterDraftState

logger = logging.getLogger(__name__)

# ── 全局 Checkpointer（进程内单例；thread_id = job_id）─────────────────
_checkpointer = MemorySaver()

# ── 活跃后台任务注册表（job_id → asyncio.Task）────────────────────────
_active_tasks: dict[str, asyncio.Task] = {}


# ═══════════════════════════════════════════════════════════════════════════
# 路由函数（conditional edges）
# ═══════════════════════════════════════════════════════════════════════════

def _route_after_blueprint(state: ChapterDraftState) -> str:
    """
    scene_planning → ? 的路由：根据 blueprint_decision 决定下一步。

    - approve：进入 draft_scenes 开始写作
    - rewrite：回到 scene_planning 重新规划（用户已注入 blueprint_directive）
    - skip：直接 END，不生成正文

    防止无限循环：iteration_count >= max_iterations 时强制 approve。
    """
    decision = state.get("blueprint_decision", "approve")
    iters = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)
    if decision == "rewrite" and iters < max_iter:
        return "scene_planning"
    if decision == "skip":
        return END
    return "draft_scenes"


def _route_after_quality(state: ChapterDraftState) -> str:
    """
    quality_check → ? 的路由：分数达标直接 debrief，否则走人工审阅节点。

    - 质检出错（score=-1）：视为达标，跳过审阅
    - 达标：直接 debrief
    - 未达标：human_review_quality
    """
    score = state.get("quality_score", -1)
    threshold = state.get("quality_threshold", 75)
    if score < 0 or score >= threshold:
        return "debrief"
    return "human_review_quality"


def _route_after_human_quality(state: ChapterDraftState) -> str:
    """
    human_review_quality → ? 的路由：根据用户决策分流。

    - accept：直接 debrief（用户认可现有质量）
    - auto_fix：auto_revision 修复后再走 quality_check
    - rewrite：回到 scene_planning 整章重写（计入 iteration_count）

    防止无限循环：达到 max_iterations 后强制 accept。
    """
    decision = state.get("quality_decision", "accept")
    iters = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)
    if iters >= max_iter:
        logger.warning("max_iterations reached, forcing accept")
        return "debrief"
    if decision == "auto_fix":
        return "auto_revision"
    if decision == "rewrite":
        return "scene_planning"
    return "debrief"


def _route_after_auto_revision(state: ChapterDraftState) -> str:
    """auto_revision → quality_check 或 debrief（达到上限时跳过再次质检）。"""
    iters = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)
    if iters >= max_iter:
        return "debrief"
    return "quality_check"


# ═══════════════════════════════════════════════════════════════════════════
# 图编译
# ═══════════════════════════════════════════════════════════════════════════

def _build_graph() -> Any:
    """构建并编译 chapter_draft StateGraph，返回 compiled graph 对象。"""
    builder: StateGraph = StateGraph(ChapterDraftState)

    # 注册节点
    builder.add_node("load_context", load_context)
    builder.add_node("scene_planning", scene_planning)
    builder.add_node("human_review_blueprint", human_review_blueprint)
    builder.add_node("draft_scenes", draft_scenes)
    builder.add_node("quality_check", quality_check)
    builder.add_node("human_review_quality", human_review_quality)
    builder.add_node("auto_revision", auto_revision)
    builder.add_node("debrief", debrief)
    builder.add_node("save_commit", save_commit)

    # 有向边
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "scene_planning")
    builder.add_edge("scene_planning", "human_review_blueprint")
    builder.add_conditional_edges(
        "human_review_blueprint",
        _route_after_blueprint,
        {"scene_planning": "scene_planning", "draft_scenes": "draft_scenes", END: END},
    )
    builder.add_edge("draft_scenes", "quality_check")
    builder.add_conditional_edges(
        "quality_check",
        _route_after_quality,
        {"debrief": "debrief", "human_review_quality": "human_review_quality"},
    )
    builder.add_conditional_edges(
        "human_review_quality",
        _route_after_human_quality,
        {
            "debrief": "debrief",
            "auto_revision": "auto_revision",
            "scene_planning": "scene_planning",
        },
    )
    builder.add_conditional_edges(
        "auto_revision",
        _route_after_auto_revision,
        {"quality_check": "quality_check", "debrief": "debrief"},
    )
    builder.add_edge("debrief", "save_commit")
    builder.add_edge("save_commit", END)

    return builder.compile(checkpointer=_checkpointer)


_draft_graph = _build_graph()


# ═══════════════════════════════════════════════════════════════════════════
# 外部接口：run_draft_job / resume_draft_job
# ═══════════════════════════════════════════════════════════════════════════

async def _execute_graph(job_id: str, graph_input: Any) -> None:
    """
    执行或 resume 图，消费 astream 事件流，捕获 interrupt 和异常。

    此函数作为 background asyncio.Task 运行，与 HTTP 请求生命周期无关。
    - interrupt：图暂停，astream 正常结束，等待 POST /input resume
    - 异常：标记 job failed，推送 job_failed 事件

    @param job_id: GenerationJob UUID 字符串，同时是 LG thread_id
    @param graph_input: 初始 state dict（首次）或 Command(resume=...) 对象（resume）
    """
    config = {"configurable": {"thread_id": job_id}}
    try:
        async for _chunk in _draft_graph.astream(
            graph_input, config, stream_mode="updates"
        ):
            # chunk 是各节点返回的 state 更新 dict；我们已在节点内 emit 事件，此处无需额外处理
            pass
    except asyncio.CancelledError:
        update_job(job_id, status="cancelled")
        emit(job_id, "job_cancelled", message="任务已取消")
        send_sentinel(job_id)
        raise
    except Exception as exc:
        logger.exception("draft_graph execution failed for job %s", job_id)
        update_job(job_id, status="failed", error_detail=str(exc))
        emit(job_id, "job_failed", message=str(exc))
        send_sentinel(job_id)
        return

    # 图正常结束（包括 interrupt 暂停后 astream 退出）：
    # - waiting_input：节点内已写入，不关闭连接，让前端继续监听
    # - completed / failed / cancelled：节点内已处理，发送哨兵关闭 WS
    # - 仍为 running：图经 END 退出但未过 save_commit（如 blueprint skip）
    #   → 视为用户主动跳过，标为 cancelled + 发哨兵，防止 WS 永久挂起
    from app.database import SessionLocal
    from app.models.generation_job import GenerationJob

    db = SessionLocal()
    try:
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        final_status = job.status if job else "unknown"
    finally:
        db.close()

    if final_status in ("completed", "failed", "cancelled"):
        send_sentinel(job_id)
    elif final_status == "running":
        # 图已终止但 save_commit 未执行（skip 分支直接走 END）
        update_job(job_id, status="cancelled")
        emit(job_id, "job_cancelled", message="任务已跳过")
        send_sentinel(job_id)


def _track_task(job_id: str, task: asyncio.Task) -> None:
    """登记 background task，任务结束后自动清理注册表。"""
    _active_tasks[job_id] = task

    def _cleanup(t: asyncio.Task) -> None:
        if _active_tasks.get(job_id) is t:
            _active_tasks.pop(job_id, None)

    task.add_done_callback(_cleanup)


async def run_draft_job(
    job_id: str,
    project_id: str,
    chapter_id: str,
    outline_node_id: str = "",
    user_directives: str = "",
    llm_provider_id: Optional[str] = None,
    model_profile: str = "gemini",
    quality_threshold: int = 75,
    skip_blueprint_review: bool = False,
    skip_quality_review: bool = False,
    max_iterations: int = 3,
) -> None:
    """
    启动 chapter_draft_graph 后台任务（从头开始）。

    应由 POST /jobs 端点在创建 GenerationJob 记录后调用，以 asyncio.create_task 包裹。

    @param job_id: GenerationJob UUID 字符串（同时作为 LG thread_id）
    @param project_id: 所属项目 UUID 字符串
    @param chapter_id: 要起草的章节 UUID 字符串
    @param outline_node_id: 对应大纲节点 UUID（无则传空串）
    @param user_directives: 用户在提交时附带的写作指令
    @param llm_provider_id: LLM provider UUID（None=使用环境变量）
    @param model_profile: "gemini" | "local"
    @param quality_threshold: 质检通过分数线（0-100）
    @param skip_blueprint_review: True=跳过蓝图人工审阅
    @param skip_quality_review: True=质检未达标时自动 auto_fix，不等待人工
    @param max_iterations: rewrite/auto_fix 最大循环次数
    """
    initial_state: ChapterDraftState = {
        "job_id": job_id,
        "project_id": project_id,
        "chapter_id": chapter_id,
        "outline_node_id": outline_node_id,
        "user_directives": user_directives,
        "llm_provider_id": llm_provider_id,
        "model_profile": model_profile,
        "quality_threshold": quality_threshold,
        "skip_blueprint_review": skip_blueprint_review,
        "skip_quality_review": skip_quality_review,
        "max_iterations": max_iterations,
        # 以下字段由各节点填充，初始给默认值
        "chapter_title": "",
        "phase": "",
        "positioning": None,
        "word_target": 2300,
        "draft_ctx": {},
        "scene_blueprint": [],
        "blueprint_decision": "",
        "blueprint_directive": "",
        "draft_content": "",
        "draft_word_count": 0,
        "quality_report": None,
        "quality_score": -1,
        "quality_decision": "",
        "quality_directive": "",
        "iteration_count": 0,
        "errors": [],
    }
    update_job(job_id, status="running", current_node="load_context", progress_pct=0)
    task = asyncio.create_task(
        _execute_graph(job_id, initial_state),
        name=f"draft-job-{job_id[:8]}",
    )
    _track_task(job_id, task)


async def resume_draft_job(job_id: str, user_input: dict) -> None:
    """
    Resume 被 interrupt 暂停的 chapter_draft_graph（human interrupt 节点唤醒）。

    应由 POST /jobs/{id}/input 端点调用，以 asyncio.create_task 包裹。

    @param job_id: 与 run_draft_job 相同的 job UUID
    @param user_input: 用户提交的决策 dict，如 {"action": "approve"} 或
                       {"action": "rewrite", "directive": "第二场改成夜袭"}
    """
    update_job(job_id, status="running")
    emit(job_id, "job_resumed", user_input=user_input)
    task = asyncio.create_task(
        _execute_graph(job_id, Command(resume=user_input)),
        name=f"draft-resume-{job_id[:8]}",
    )
    _track_task(job_id, task)


def cancel_draft_job(job_id: str) -> bool:
    """
    取消任务：无论是否有活跃 asyncio Task，都更新 DB 状态 + 发事件 + 关闭 WS。

    waiting_input 暂停期间没有活跃 Task，但需要同样标记 cancelled 并发哨兵，
    防止前端 WS 永久挂起。

    @returns True=找到并取消了活跃 Task，False=无活跃 Task（但 DB 仍已更新）
    """
    update_job(job_id, status="cancelled")
    emit(job_id, "job_cancelled", message="任务已取消")
    send_sentinel(job_id)

    task = _active_tasks.get(job_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


# re-export for __init__.py
__all__ = [
    "run_draft_job",
    "resume_draft_job",
    "cancel_draft_job",
    "subscribe",
    "unsubscribe",
]
