"""
bootstrap_graph.py — LangGraph Bootstrap 路由

资源边界：
  本模块负责「创建运行 → SSE 事件流 → 用户确认闸门 → Resume」全链路的 HTTP/SSE 层。
  AI 生成逻辑和图执行全部委托给 services/bootstrap/graph.py。
  旧的 /bootstrap/stream（SSE 直连）在 routers/generate.py 中继续保留，两套并存。

端点：
  POST   /bootstrap/runs                    创建运行并启动后台任务
  GET    /bootstrap/runs/{run_id}           查询运行状态（含已完成事件）
  GET    /bootstrap/runs/{run_id}/events    SSE 实时事件流
  POST   /bootstrap/runs/{run_id}/resume    用户确认/修改立项定位后继续

SSE 协议（JSON lines，prefix: data:）：
  step_start    — {"step": "positioning", "label": "..."}
  step_done     — {"step": "...", "count": N, "preview": "..."}
  gate_pending  — {"step": "positioning", "positioning": {...}, "message": "..."}
  gate_passed   — {"positioning": {...}}
  error         — {"step": "...", "message": "..."}
  complete      — {"project_id": "uuid"}
  __stream_end__— 内部哨兵，触发 SSE 连接关闭（不转发到客户端）

代码红线：本文件 < 300 行。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.bootstrap_run import BootstrapRun
from app.models.user import User
from app.services.bootstrap.graph import (
    run_bootstrap,
    resume_bootstrap,
    subscribe,
    unsubscribe,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bootstrap", tags=["bootstrap-graph"])


# ──────────────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────────────

class StartRequest(BaseModel):
    """POST /bootstrap/runs 请求体。"""
    logline: str
    premise: Optional[str] = ""
    target_words: int = 1_200_000
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None


class ResumeRequest(BaseModel):
    """
    POST /bootstrap/runs/{run_id}/resume 请求体。

    positioning 为用户在前端确认或编辑后的立项定位 JSON；
    若用户未修改直接点确认，传回原 gate_data.positioning 即可。
    """
    positioning: dict
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None


class RunStatus(BaseModel):
    """GET /bootstrap/runs/{run_id} 响应体。"""
    run_id: str
    status: str
    project_id: Optional[str]
    gate_data: Optional[dict]
    events: list[dict]
    error_message: Optional[str]


class RunHistoryItem(BaseModel):
    """项目下的单次 Bootstrap 运行摘要。"""
    run_id: str
    status: str
    project_id: Optional[str]
    gate_data: Optional[dict]
    events: list[dict]
    error_message: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


# ──────────────────────────────────────────────────────
# 端点实现
# ──────────────────────────────────────────────────────

@router.post("/runs", summary="创建 Bootstrap 运行并启动后台任务")
async def create_run(
    req: StartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    创建 BootstrapRun 记录，启动后台 asyncio 任务执行 LangGraph 图。

    图执行到 positioning 节点后暂停（interrupt_before=["gate"]），
    SSE 流推送 gate_pending 事件；前端展示立项定位确认面板。

    @returns {"run_id": "uuid"}；前端用此 id 订阅 /events 并提交 /resume
    """
    run = BootstrapRun(
        user_id=current_user.id,
        logline=req.logline,
        mode="sequential",
        model_profile=req.model_profile,
        status="pending",
        events=[],
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = str(run.id)

    # 启动后台任务（不阻塞 HTTP 响应）
    asyncio.create_task(
        run_bootstrap(
            run_id,
            logline=req.logline,
            premise=req.premise or "",
            target_words=req.target_words,
            model_profile=req.model_profile,
            llm_provider_id=req.llm_provider_id,
            user_id=current_user.id,
        ),
        name=f"bootstrap-{run_id[:8]}",
    )
    return {"run_id": run_id}


@router.get("/runs/{run_id}", summary="查询运行状态")
async def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RunStatus:
    """
    返回 BootstrapRun 当前状态快照，包含已持久化的事件日志。

    可用于：重连后判断当前阶段、前端轮询判断是否已进入 awaiting_gate。

    @raises 404: run_id 不存在或不属于当前用户
    """
    run = _get_owned_run(db, run_id, current_user.id)
    return RunStatus(
        run_id=str(run.id),
        status=run.status,
        project_id=str(run.project_id) if run.project_id else None,
        gate_data=run.gate_data,
        events=list(run.events or []),
        error_message=run.error_message,
    )


@router.get("/projects/{project_id}/runs", summary="按项目查询 Bootstrap 运行记录")
async def list_project_runs(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RunHistoryItem]:
    """
    返回指定项目下当前用户触发的 Bootstrap 运行历史（按创建时间倒序）。

    用途：
      1) 书架详情页展示「生成纪要」历史
      2) 页面重进时恢复 running/awaiting_gate run 的实时事件订阅
    """
    rows = (
        db.query(BootstrapRun)
        .filter(
            BootstrapRun.project_id == project_id,
            BootstrapRun.user_id == current_user.id,
        )
        .order_by(BootstrapRun.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        RunHistoryItem(
            run_id=str(r.id),
            status=r.status,
            project_id=str(r.project_id) if r.project_id else None,
            gate_data=r.gate_data,
            events=list(r.events or []),
            error_message=r.error_message,
            created_at=r.created_at.isoformat() if r.created_at else None,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )
        for r in rows
    ]


@router.get("/runs/{run_id}/events", summary="SSE 实时事件流")
async def stream_events(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    SSE 事件流：先 replay 已持久化事件，再订阅实时队列。

    重连语义：客户端断线重连时先收到之前所有事件，然后继续接收新事件。
    若运行已结束（done/failed），replay 完毕后直接关闭连接。

    @raises 404: run_id 不存在或不属于当前用户
    """
    run = _get_owned_run(db, run_id, current_user.id)
    past_events = list(run.events or [])
    already_done = run.status in ("done", "failed")

    async def event_generator():
        # ① replay 已持久化事件
        for ev in past_events:
            yield _sse(ev)

        if already_done:
            return

        # ② 订阅实时队列
        q = subscribe(run_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"   # SSE keepalive（不是 data 行）
                    continue
                if payload.get("event") == "__stream_end__":
                    break
                yield _sse(payload)
        finally:
            unsubscribe(run_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/resume", summary="用户确认立项定位，继续生成")
async def resume_run(
    run_id: str,
    req: ResumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    用户在前端确认（或编辑）立项定位后调用此端点，继续执行图的后半段。

    前置条件：run.status == "awaiting_gate"；否则返回 409。
    后台任务从 MemorySaver checkpoint 恢复，gate 节点接收用户的 positioning 继续执行。

    @raises 404: run 不存在或不属于当前用户
    @raises 409: run 当前状态不允许 resume
    @returns {"ok": true, "run_id": "..."}
    """
    run = _get_owned_run(db, run_id, current_user.id)
    if run.status != "awaiting_gate":
        raise HTTPException(
            status_code=409,
            detail=f"Run is in status '{run.status}', expected 'awaiting_gate'",
        )

    asyncio.create_task(
        resume_bootstrap(
            run_id,
            req.positioning,
            model_profile=req.model_profile,
            llm_provider_id=req.llm_provider_id,
            user_id=current_user.id,
        ),
        name=f"bootstrap-resume-{run_id[:8]}",
    )
    return {"ok": True, "run_id": run_id}


# ──────────────────────────────────────────────────────
# 内部辅助
# ──────────────────────────────────────────────────────

def _get_owned_run(db: Session, run_id: str, user_id) -> BootstrapRun:
    """
    查询 BootstrapRun 并校验归属，不存在或不属于当前用户时抛 404。

    @raises HTTPException 404
    """
    run = db.query(BootstrapRun).filter(BootstrapRun.id == run_id).first()
    if not run or (run.user_id and str(run.user_id) != str(user_id)):
        raise HTTPException(status_code=404, detail="Bootstrap run not found")
    return run


def _sse(payload: dict) -> str:
    """将 event dict 序列化为 SSE 数据行（`data: {...}\\n\\n`）。"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
