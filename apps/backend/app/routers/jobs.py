"""
jobs.py — 生成任务队列 API（chapter_draft / scene_plan / outline_expand）。

资源边界：
  本模块负责任务生命周期的 HTTP 层：创建、查询、注入用户输入、WebSocket 续流、取消。
  AI 生成逻辑全部委托给 services/draft_graph/。

端点：
  POST   /jobs                        提交任务，返回 job_id
  GET    /jobs/{job_id}               查询任务状态与元信息
  GET    /jobs?project_id=&status=    按项目/状态列举任务
  POST   /jobs/{job_id}/input         注入用户决策（resume human interrupt）
  WS     /jobs/{job_id}/stream        实时事件流（支持断线重连 replay）
  POST   /jobs/{job_id}/cancel        取消任务

SSE/WS 事件协议（JSON）：
  node_start      — {"node": "draft_scenes", "progress_pct": 65}
  token           — {"content": "夜风..."} （高频，不写 DB）
  node_done       — {"node": "quality_check", "score": 82}
  waiting_input   — {"schema": {"type": "blueprint_review", ...}}
  job_complete    — {"chapter_id": "...", "word_count": 2800, "quality_score": 84}
  job_failed      — {"message": "..."}
  job_cancelled   — {"message": "用户已取消"}
  __stream_end__  — 内部哨兵，触发 WS 连接关闭（不转发）

代码红线：本文件 ≤ 400 行。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Chapter
from app.models.generation_job import GenerationJob
from app.models.user import User
from app.services.draft_graph.events import subscribe, unsubscribe
from app.services.draft_graph.graph import (
    cancel_draft_job,
    resume_draft_job,
    run_draft_job,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["generation-jobs"])

# ── 活跃 resume 任务追踪（防止重复 resume）────────────────────────────
_resume_tasks: dict[str, asyncio.Task] = {}


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic Schemas
# ═══════════════════════════════════════════════════════════════════════════

class CreateJobRequest(BaseModel):
    """POST /jobs 请求体。"""

    project_id: UUID = Field(..., description="所属项目 UUID")
    job_type: Literal["chapter_draft"] = Field(
        "chapter_draft", description="任务类型（当前仅支持 chapter_draft）"
    )
    chapter_id: UUID = Field(..., description="要起草的章节 UUID")
    outline_node_id: Optional[UUID] = Field(
        None, description="对应大纲节点 UUID（可选）"
    )
    user_directives: str = Field("", description="本次生成的自定义写作指令")
    llm_provider_id: Optional[UUID] = Field(None, description="指定 LLM provider")
    model_profile: Literal["gemini", "local"] = Field("gemini")
    quality_threshold: int = Field(75, ge=0, le=100, description="质检通过分数线")
    skip_blueprint_review: bool = Field(
        False, description="True=跳过场景蓝图人工审阅直接起笔"
    )
    skip_quality_review: bool = Field(
        False, description="True=质检未达标时自动 auto_fix，不等待人工"
    )
    max_iterations: int = Field(3, ge=1, le=5, description="rewrite/auto_fix 最大循环次数")


class JobInputRequest(BaseModel):
    """POST /jobs/{job_id}/input 请求体 — 用户注入决策。"""

    action: str = Field(
        ...,
        description=(
            "蓝图审阅：'approve' | 'rewrite' | 'skip'\n"
            "质检审阅：'accept' | 'auto_fix' | 'rewrite'"
        ),
    )
    directive: str = Field("", description="rewrite 时附带的具体修改指令")


class JobStatus(BaseModel):
    """GET /jobs/{job_id} 响应体。"""

    job_id: str
    project_id: str
    job_type: str
    status: str
    current_node: Optional[str]
    progress_pct: int
    user_input_schema: Optional[dict]
    result: Optional[dict]
    error_detail: Optional[str]
    events: list[dict]
    created_at: Optional[str]
    updated_at: Optional[str]


class JobListItem(BaseModel):
    """GET /jobs 列表项。"""

    job_id: str
    project_id: str
    job_type: str
    status: str
    current_node: Optional[str]
    progress_pct: int
    result: Optional[dict]
    created_at: Optional[str]


# ═══════════════════════════════════════════════════════════════════════════
# 端点实现
# ═══════════════════════════════════════════════════════════════════════════

@router.post("", summary="提交生成任务")
async def create_job(
    req: CreateJobRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    创建 GenerationJob 记录并启动后台 LangGraph 任务。

    任务在后台 asyncio Task 中运行，与 HTTP 连接生命周期无关，前端断线不影响执行。

    @returns {"job_id": "uuid"}
    @raises 404: chapter 不存在或不属于 project_id
    """
    # 验证 chapter 归属（防止跨项目构造 chapter_id 攻击）
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id,
        Chapter.project_id == req.project_id,
    ).first()
    if not chapter:
        raise HTTPException(
            status_code=404,
            detail="Chapter not found or does not belong to the specified project",
        )

    job = GenerationJob(
        project_id=req.project_id,
        user_id=current_user.id,
        job_type=req.job_type,
        status="pending",
        input_payload={
            "chapter_id": str(req.chapter_id),
            "outline_node_id": str(req.outline_node_id) if req.outline_node_id else "",
            "user_directives": req.user_directives,
            "llm_provider_id": str(req.llm_provider_id) if req.llm_provider_id else None,
            "model_profile": req.model_profile,
            "quality_threshold": req.quality_threshold,
            "skip_blueprint_review": req.skip_blueprint_review,
            "skip_quality_review": req.skip_quality_review,
            "max_iterations": req.max_iterations,
        },
        events=[],
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = str(job.id)

    # 启动后台任务（不 await，与请求解耦）
    asyncio.create_task(
        run_draft_job(
            job_id=job_id,
            project_id=str(req.project_id),
            chapter_id=str(req.chapter_id),
            outline_node_id=str(req.outline_node_id) if req.outline_node_id else "",
            user_directives=req.user_directives,
            llm_provider_id=str(req.llm_provider_id) if req.llm_provider_id else None,
            model_profile=req.model_profile,
            quality_threshold=req.quality_threshold,
            skip_blueprint_review=req.skip_blueprint_review,
            skip_quality_review=req.skip_quality_review,
            max_iterations=req.max_iterations,
        ),
        name=f"draft-job-{job_id[:8]}",
    )
    return {"job_id": job_id}


@router.get("", summary="按项目列举生成任务")
async def list_jobs(
    project_id: UUID = Query(..., description="项目 UUID"),
    status: Optional[str] = Query(None, description="过滤状态"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[JobListItem]:
    """
    返回指定项目下当前用户的生成任务列表（最近 N 条，倒序）。

    @param project_id: 必填，限定项目范围
    @param status: 可选，过滤状态（pending/running/waiting_input/completed/failed/cancelled）
    @param limit: 最多返回条数，默认 20
    """
    query = db.query(GenerationJob).filter(
        GenerationJob.project_id == project_id,
        GenerationJob.user_id == current_user.id,
    )
    if status:
        query = query.filter(GenerationJob.status == status)
    jobs = query.order_by(GenerationJob.created_at.desc()).limit(limit).all()

    return [
        JobListItem(
            job_id=str(j.id),
            project_id=str(j.project_id),
            job_type=j.job_type,
            status=j.status,
            current_node=j.current_node,
            progress_pct=j.progress_pct,
            result=j.result,
            created_at=j.created_at.isoformat() if j.created_at else None,
        )
        for j in jobs
    ]


@router.get("/{job_id}", summary="查询任务状态")
async def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobStatus:
    """
    返回任务完整状态快照，含已持久化的事件日志（用于重连后 replay）。

    @raises 404: job_id 不存在或不属于当前用户
    """
    job = _get_owned_job(db, job_id, current_user.id)
    return _to_job_status(job)


@router.post("/{job_id}/input", summary="注入用户决策（resume human interrupt）")
async def inject_input(
    job_id: str,
    req: JobInputRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    在 waiting_input 状态的任务中注入用户决策，触发 LangGraph resume。

    前置条件：job.status == "waiting_input"；否则返回 409。
    后台任务以 Command(resume=user_input) 继续执行图。

    @raises 404: job 不存在或不属于当前用户
    @raises 409: job 当前状态不允许注入输入
    @returns {"ok": true, "job_id": "..."}
    """
    job = _get_owned_job(db, job_id, current_user.id)
    if job.status != "waiting_input":
        raise HTTPException(
            status_code=409,
            detail=f"Job is in status '{job.status}', expected 'waiting_input'",
        )

    user_input = {"action": req.action, "directive": req.directive}
    job.user_input = user_input
    db.commit()

    # 避免重复 resume（防止双击）
    if job_id in _resume_tasks and not _resume_tasks[job_id].done():
        raise HTTPException(status_code=409, detail="Resume already in progress")

    task = asyncio.create_task(
        resume_draft_job(job_id, user_input),
        name=f"draft-resume-{job_id[:8]}",
    )
    _resume_tasks[job_id] = task
    task.add_done_callback(lambda _: _resume_tasks.pop(job_id, None))

    return {"ok": True, "job_id": job_id}


@router.post("/{job_id}/cancel", summary="取消任务")
async def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    取消正在运行或等待中的任务。

    - running / waiting_input：取消后台 asyncio Task 并标记 cancelled
    - 已终态（completed / failed / cancelled）：直接返回当前状态，不报错

    @raises 404: job 不存在或不属于当前用户
    """
    job = _get_owned_job(db, job_id, current_user.id)
    if job.status in ("completed", "failed", "cancelled"):
        return {"ok": True, "job_id": job_id, "status": job.status}

    cancel_draft_job(job_id)
    return {"ok": True, "job_id": job_id, "status": "cancelled"}


@router.websocket("/{job_id}/stream")
async def stream_job(job_id: str, websocket: WebSocket) -> None:
    """
    WebSocket 实时事件流端点（支持断线重连 replay）。

    协议：
      1. 连接后立即 replay 所有已持久化的 events（`events` 字段）
      2. 若任务已终态，replay 完毕后关闭连接
      3. 否则进入实时订阅循环，token 级 events 实时推送
      4. 收到 __stream_end__ 哨兵后关闭连接

    鉴权：通过 query param `token=<jwt>` 传入（避免 WS 不支持 Authorization header）。

    @param job_id: GenerationJob UUID 字符串
    """
    await websocket.accept()

    # ── 简易 token 鉴权（query param）──────────────────────────────────
    token = websocket.query_params.get("token", "")
    current_user = await _ws_auth(token)
    if current_user is None:
        await websocket.send_json({"event": "error", "message": "Unauthorized"})
        await websocket.close(code=4001)
        return

    # ── 读取已持久化事件，同步 replay ───────────────────────────────────
    db = next(get_db())
    try:
        job = _get_owned_job(db, job_id, current_user.id)
        past_events = list(job.events or [])
        already_done = job.status in ("completed", "failed", "cancelled")
    except HTTPException:
        await websocket.send_json({"event": "error", "message": "Job not found"})
        await websocket.close(code=4004)
        return
    finally:
        db.close()

    for ev in past_events:
        if ev.get("event") == "__stream_end__":
            continue
        try:
            await websocket.send_json(ev)
        except WebSocketDisconnect:
            return

    if already_done:
        await websocket.close()
        return

    # ── 订阅实时队列 ────────────────────────────────────────────────────
    q = subscribe(job_id)
    try:
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # 发送 ping 保活
                try:
                    await websocket.send_json({"event": "ping"})
                except WebSocketDisconnect:
                    return
                continue

            if payload.get("event") == "__stream_end__":
                break
            try:
                await websocket.send_json(payload)
            except WebSocketDisconnect:
                return
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe(job_id, q)
        try:
            await websocket.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# 内部辅助
# ═══════════════════════════════════════════════════════════════════════════

def _get_owned_job(db: Session, job_id: str, user_id) -> GenerationJob:
    """
    查询 GenerationJob 并校验归属，不存在或不属于当前用户时抛 404。

    @raises HTTPException 404
    """
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job or str(job.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="Generation job not found")
    return job


def _to_job_status(job: GenerationJob) -> JobStatus:
    """将 GenerationJob ORM 对象转换为响应 schema。"""
    return JobStatus(
        job_id=str(job.id),
        project_id=str(job.project_id),
        job_type=job.job_type,
        status=job.status,
        current_node=job.current_node,
        progress_pct=job.progress_pct,
        user_input_schema=job.user_input_schema,
        result=job.result,
        error_detail=job.error_detail,
        events=list(job.events or []),
        created_at=job.created_at.isoformat() if job.created_at else None,
        updated_at=job.updated_at.isoformat() if job.updated_at else None,
    )


async def _ws_auth(token: str) -> Optional[User]:
    """
    WebSocket 简易 JWT 鉴权（从 query param token= 读取）。

    与 HTTP Bearer token 使用相同的 JWT 解码逻辑。
    返回 User 对象，鉴权失败返回 None。
    """
    if not token:
        return None
    try:
        from app.utils.auth import decode_access_token
        from app.database import SessionLocal

        payload = decode_access_token(token)
        user_id = payload.get("sub") if payload else None
        if not user_id:
            return None
        db = SessionLocal()
        try:
            from app.models.user import User
            return db.query(User).filter(User.id == user_id).first()
        finally:
            db.close()
    except Exception:
        return None
