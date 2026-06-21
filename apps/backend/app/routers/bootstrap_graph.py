"""
bootstrap_graph.py — LangGraph Bootstrap 路由

资源边界：
  本模块负责「创建运行 → SSE 事件流 → 用户确认闸门 → Resume」全链路的 HTTP/SSE 层。
  AI 生成逻辑和图执行全部委托给 services/bootstrap/graph.py。
  旧的 /bootstrap/stream 端点（generate.py）已废弃并清空，唯一入口为本文件。

端点：
  POST   /bootstrap/runs                    创建运行并启动后台任务
  GET    /bootstrap/runs/{run_id}           查询运行状态（含已完成事件）
  GET    /bootstrap/runs/{run_id}/events    SSE 实时事件流
  POST   /bootstrap/runs/{run_id}/resume    用户确认/修改立项定位后继续

SSE 协议（JSON lines，prefix: data:）：
  每条事件含 ``ts``（服务端毫秒时间戳），重连回放时用于还原各步耗时。
  step_start    — {"step": "positioning", "label": "..."}
  step_done     — {"step": "...", "count": N, "preview": "..."}
  gate_pending  — {"step": "positioning|power_systems|characters|volumes", "message": "...", "positioning": {...}?, "gate_preview": {...}?}
  gate_passed   — {"step": "...", "positioning": {...}?}
  error         — {"step": "...", "message": "..."}
  step_halted   — {"step": "...", "message": "..."}  # 步骤失败已暂停，等待 retry_step
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
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.bootstrap_run import BootstrapRun
from app.models.user import User
from app.services.bootstrap.graph import (
    emit,
    get_graph_for_mode,
    subscribe,
    unsubscribe,
)
from app.services.bootstrap.pipeline.runner import resume_pipeline, run_pipeline
from app.services.bootstrap.pipeline.styles import get_style
from app.schemas.bootstrap_dabai_positioning import try_validate_dabai_positioning
from app.schemas.bootstrap_positioning import try_validate_positioning

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bootstrap", tags=["bootstrap-graph"])
_RUN_TASKS: dict[str, asyncio.Task] = {}


def _track_task(run_id: str, task: asyncio.Task) -> None:
    """登记后台 run 任务，并在结束后自动清理。"""
    _RUN_TASKS[run_id] = task

    def _cleanup(_t: asyncio.Task) -> None:
        if _RUN_TASKS.get(run_id) is _t:
            _RUN_TASKS.pop(run_id, None)

    task.add_done_callback(_cleanup)


# ──────────────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────────────

class StartRequest(BaseModel):
    """POST /bootstrap/runs 请求体。

    mode 说明：
    - ``sequential``：通用串行流程（默认），适合起点/晋江向或自定义题材
    - ``doupo``：斗破·大白文玄幻，基于通用线，单斗气主轴 + 势力/功法/法宝三合一 + 精简设定，禁修仙/禁上帝视角
    - ``xianxia``：番茄·玄幻修仙直白，境界进度由「境界预算契约」硬执行（杜绝第一卷修满）
    - ``dabai``：大白文·修仙，约4次LLM Bootstrap；卷纲定地图+境界区间，章纲懒展开定具体境界

    注：番茄（fanqie）分支已下线，由 doupo 取代。
    """
    logline: str
    premise: Optional[str] = ""
    target_words: int = 1_200_000
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None
    mode: Literal["sequential", "doupo", "xianxia", "dabai"] = "sequential"
    auto_mode: bool = False
    # 写作风格档位（作者建书时一次性选择，全书贯彻）：
    # - ``plain``    白话直白：句子短、新名词就近解释、放松密度约束，降低阅读门槛（小白友好）
    # - ``standard`` 默认：保持现状，行为完全不变
    # - ``dense``    老白文：保持/强化信息密度与文采
    # 落到 Project.extra.writing_style + Project.extra.positioning.writing_style，
    # 由设定生成（power_systems/factions/settings）与正文写作（draft_assist_stream）读取。
    writing_style: Literal["plain", "standard", "dense"] = "standard"


class ResumeRequest(BaseModel):
    """
    POST /bootstrap/runs/{run_id}/resume 请求体。

    - 立项闸门（step positioning）：须带 ``positioning``（或依赖 gate_data 中的备份）；
      ``action=regenerate`` 时忽略 positioning，由后端重新调用 Step 0。
    - 其他闸门（境界 / 人物 / 卷骨架）：仅需 ``action``；``regenerate`` 会删除本步产物并重跑。
    - 步骤失败暂停（status=awaiting_retry）：``action=retry_step`` 且 ``step`` 与 gate_data.step 一致。
    """
    action: Literal["approve", "regenerate", "retry_step"] = "approve"
    step: Optional[str] = None
    positioning: Optional[dict] = None
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None


class RunStatus(BaseModel):
    """GET /bootstrap/runs/{run_id} 响应体。"""
    run_id: str
    status: str
    mode: str = "sequential"
    project_id: Optional[str]
    gate_data: Optional[dict]
    events: list[dict]
    error_message: Optional[str]
    logline: Optional[str] = None
    created_at: Optional[str] = None


class RunHistoryItem(BaseModel):
    """项目下的单次 Bootstrap 运行摘要。"""
    run_id: str
    status: str
    project_id: Optional[str]
    gate_data: Optional[dict]
    events: list[dict]
    error_message: Optional[str]
    logline: Optional[str] = None
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
    from app.services.bootstrap.gate_auto import merge_gate_data_with_auto_mode

    run = BootstrapRun(
        user_id=current_user.id,
        logline=req.logline,
        mode=req.mode,
        model_profile=req.model_profile,
        status="pending",
        events=[],
        gate_data=merge_gate_data_with_auto_mode(
            None, req.auto_mode, llm_provider_id=req.llm_provider_id,
        ),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    run_id = str(run.id)

    style = get_style(req.mode)
    _effective_ws = req.writing_style
    if req.mode in ("doupo", "xianxia", "dabai") and _effective_ws == "standard":
        _effective_ws = "plain"
    graph = get_graph_for_mode(req.mode)

    async def _run() -> None:
        await run_pipeline(
            graph,
            style,
            run_id,
            logline=req.logline,
            premise=req.premise or "",
            target_words=req.target_words,
            model_profile=req.model_profile,
            llm_provider_id=req.llm_provider_id,
            user_id=current_user.id,
            writing_style=_effective_ws,
        )

    task = asyncio.create_task(_run(), name=f"bootstrap-{req.mode}-{run_id[:8]}")
    _track_task(run_id, task)
    return {"run_id": run_id, "mode": req.mode}


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
        mode=run.mode or "sequential",
        project_id=str(run.project_id) if run.project_id else None,
        gate_data=run.gate_data,
        events=list(run.events or []),
        error_message=run.error_message,
        logline=run.logline,
        created_at=run.created_at.isoformat() if run.created_at else None,
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
            logline=r.logline,
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
    already_done = run.status in ("done", "failed", "cancelled")

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


@router.post("/runs/{run_id}/resume", summary="用户确认闸门或重试失败步骤，继续生成")
async def resume_run(
    run_id: str,
    req: ResumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    用户确认闸门、或重试失败步骤后调用，从 LangGraph checkpoint 继续。

    - ``awaiting_gate``：approve / regenerate（立项须 positioning）
    - ``awaiting_retry``：仅 ``retry_step``，且 ``step`` 须与 gate_data 中记录一致

    @raises 404: run 不存在或不属于当前用户
    @raises 409: run 当前状态不允许 resume
    @returns {"ok": true, "run_id": "..."}
    """
    run = _get_owned_run(db, run_id, current_user.id)
    gd = run.gate_data if isinstance(run.gate_data, dict) else {}
    recovered_from_failed = False
    step_retry_pending = gd.get("kind") == "step_retry" or run.status == "awaiting_retry"
    if step_retry_pending and run.status != "awaiting_retry":
        run.status = "awaiting_retry"
        run.error_message = None
        db.commit()
    # 番茄线等步骤异常落 failed（无 interrupt）时，允许 retry_step 从 checkpoint 续跑
    if run.status == "failed" and req.action == "retry_step":
        step = (req.step or "").strip() or _infer_failed_step_from_events(run.events or [])
        if not step:
            raise HTTPException(
                status_code=422,
                detail="无法识别失败步骤，请指定 step 参数（如 rhythm_map）",
            )
        fail_msg = (run.error_message or f"步骤 {step} 失败，请重试")[:500]
        run.status = "awaiting_retry"
        run.error_message = None
        run.gate_data = {
            **gd,
            "kind": "step_retry",
            "step": step,
            "message": fail_msg,
        }
        db.commit()
        gd = run.gate_data if isinstance(run.gate_data, dict) else {}
        step_retry_pending = True
        recovered_from_failed = True
    # 闸门 UI 仍可见但 resume 因异常落 failed 时，允许在 gate 上下文恢复
    elif run.status == "failed" and req.action in ("approve", "regenerate") and gd.get("current_gate"):
        run.status = "awaiting_gate"
        run.error_message = None
        db.commit()
        step_retry_pending = False
    elif step_retry_pending:
        if req.action != "retry_step":
            failed = gd.get("step") or "memory"
            raise HTTPException(
                status_code=409,
                detail=(
                    f"当前等待重试步骤「{failed}」，请使用 "
                    f'action=retry_step 且 step="{failed}"，不可使用 approve'
                ),
            )
    elif run.status not in ("awaiting_gate", "awaiting_retry"):
        raise HTTPException(
            status_code=409,
            detail=f"Run is in status '{run.status}', expected 'awaiting_gate' or 'awaiting_retry'",
        )

    graph = get_graph_for_mode(run.mode or "sequential")

    async def _resume() -> None:
        await resume_pipeline(
            graph,
            run_id,
            _build_resume_payload(run, req),
            model_profile=req.model_profile,
            llm_provider_id=req.llm_provider_id,
            user_id=current_user.id,
            recovered_from_failed=recovered_from_failed,
        )

    task = asyncio.create_task(
        _resume(),
        name=f"bootstrap-resume-{run.mode}-{run_id[:8]}",
    )
    _track_task(run_id, task)
    return {"ok": True, "run_id": run_id}


@router.post("/runs/{run_id}/cancel", summary="取消正在执行的 Bootstrap 运行")
async def cancel_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    取消 run（若后台任务仍在执行会主动 task.cancel()）。

    - 状态会标记为 cancelled
    - SSE 会收到 cancelled 事件
    """
    run = _get_owned_run(db, run_id, current_user.id)
    if run.status in ("done", "failed", "cancelled"):
        return {"ok": True, "run_id": run_id, "status": run.status}

    task = _RUN_TASKS.get(run_id)
    if task and not task.done():
        task.cancel()

    emit(run_id, "cancelled", db, persist_status="cancelled", message="用户已取消生成")
    return {"ok": True, "run_id": run_id, "status": "cancelled"}


# ──────────────────────────────────────────────────────
# 内部辅助
# ──────────────────────────────────────────────────────


def _infer_failed_step_from_events(events: list) -> str:
    """从已持久化 SSE 事件中推断最近失败步骤（用于 failed run 恢复）。"""
    for ev in reversed(events or []):
        if not isinstance(ev, dict):
            continue
        if ev.get("event") not in ("error", "step_halted"):
            continue
        step = str(ev.get("step") or "").strip()
        if step:
            return step
    return ""


def _build_resume_payload(run: BootstrapRun, req: ResumeRequest) -> dict:
    """
    将 HTTP 请求体转为 LangGraph ``Command(resume=...)`` 用的扁平 dict。

    立项闸门：校验 / 归一化 positioning；approve 时可从 gate_data 回退未改动的备份。
    其他闸门：仅转发 action。
    步骤失败：retry_step + step 校验。
    """
    gd = run.gate_data if isinstance(run.gate_data, dict) else {}
    if gd.get("kind") == "step_retry" or run.status == "awaiting_retry":
        expected = str(gd.get("step") or "")
        if req.action != "retry_step":
            raise HTTPException(status_code=409, detail="当前仅允许 retry_step")
        step = (req.step or "").strip()
        if not step or step != expected:
            raise HTTPException(
                status_code=422,
                detail=f"请重试步骤 {expected or '（未知）'}",
            )
        return {"action": "retry_step", "step": step}

    kind = gd.get("kind") or "positioning"
    if kind == "positioning":
        if req.action == "regenerate":
            return {"action": "regenerate"}
        raw = req.positioning if req.positioning is not None else gd.get("positioning")
        if not isinstance(raw, dict) or not raw:
            raise HTTPException(status_code=422, detail="缺少有效的 positioning，无法通过立项闸门")
        if run.mode == "dabai":
            benchmark = gd.get("benchmark") if isinstance(gd.get("benchmark"), dict) else None
            normalized, err = try_validate_dabai_positioning(raw, benchmark=benchmark)
        elif run.mode in ("xianxia", "doupo"):
            # 斗破立项产物字段集与修仙线一致，复用同一校验，无需新增 schema
            from app.schemas.bootstrap_xianxia_positioning import (
                try_validate_xianxia_positioning,
            )
            normalized, err = try_validate_xianxia_positioning(raw)
        else:
            normalized, err = try_validate_positioning(raw)
        if err or normalized is None:
            raise HTTPException(status_code=422, detail=err or "positioning 校验失败")
        return {"action": "approve", "positioning": normalized}
    return {"action": req.action}


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
