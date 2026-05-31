"""
bootstrap_step_regen.py — Bootstrap 单步独立重跑路由

资源边界：
  仅负责 HTTP/SSE 层；实际 ctx 重建、wipe、dispatch 全部委托
  services/bootstrap/step_regen.py。

端点：
  POST /bootstrap/projects/{project_id}/steps/{step}/regenerate
    — 清除该步骤 DB 产物 → 重跑 → SSE 推送 step_start / step_done / error

SSE 事件（与主流程兼容，key=step 与 StepKey 一致）：
  step_start   — {"event": "step_start", "step": "<step>", "label": "..."}
  step_done    — {"event": "step_done",  "step": "...", "count": N, "preview": "..."}
  error        — {"event": "error",      "step": "...", "message": "..."}
  __stream_end__  内部哨兵，前端侦测到后关闭 SSE

代码红线：本文件 < 130 行。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models import Project
from app.services.bootstrap.step_regen import build_full_ctx, dispatch_regen, wipe_step
from app.services.generation_service import GenerationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bootstrap", tags=["bootstrap-step-regen"])

# 支持独立重跑的步骤白名单
# 注意：vol1_chapters / ch1_scenes 已从 Bootstrap 移除，不再支持独立重跑。
_SUPPORTED_STEPS = frozenset({
    "power_systems", "factions", "storylines", "characters",
    "skills", "items", "settings",
    "volumes", "memory", "relations",
    "opening_contract", "core_mysteries",
    "consistency", "emotion_arc", "villain_arc",
})


class StepRegenRequest(BaseModel):
    """POST …/regenerate 请求体（可选，主要用于传 llm_provider_id）。"""
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _emit_payload(step: str, event: str, **kwargs) -> dict:
    return {"event": event, "step": step, "ts": int(time.time() * 1000), **kwargs}


@router.post(
    "/projects/{project_id}/steps/{step}/regenerate",
    summary="单步重新生成（SSE）",
)
async def regenerate_step(
    project_id: str,
    step: str,
    req: StepRegenRequest = StepRegenRequest(),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    清除目标步骤的 DB 产物，重跑生成，以 SSE 流推送进度事件。

    前端订阅后，将收到与主 Bootstrap 流程相同格式的 step_start / step_done / error，
    可直接复用 useBootstrapStream 的 handleEvent 更新步骤状态。

    @raises 404: 项目不存在或不属于当前用户
    @raises 400: 步骤名不在白名单
    """
    if step not in _SUPPORTED_STEPS:
        raise HTTPException(status_code=400, detail=f"步骤 '{step}' 不支持独立重跑")

    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    _STEP_LABELS: dict[str, str] = {
        "power_systems": "重新生成境界体系…",
        "factions": "重新生成势力体系…",
        "storylines": "重新生成故事线…",
        "characters": "重新生成人物库…",
        "skills": "重新生成核心技能…",
        "items": "重新生成关键道具…",
        "settings": "重新生成世界观设定…",
        "volumes": "重新规划卷级结构…",
        "memory": "重新注入记忆种子…",
        "relations": "重新建立人物关系…",
        "opening_contract": "重新规划开局承诺…",
        "core_mysteries": "重新分配核心谜题…",
        "consistency": "重新扫描一致性…",
        "emotion_arc": "重新规划情绪节律…",
        "villain_arc": "重新规划反派行动线…",
    }
    label = _STEP_LABELS.get(step, f"重新生成 {step}…")

    async def event_stream():
        """清理 → 重跑 → 推送进度；异常时推送 error 事件。"""
        try:
            # ① 通知前端：步骤开始（在主线程 wipe 之前告知，避免前端无反应）
            yield _sse(_emit_payload(step, "step_start", label=label))

            # ② 卷级重跑：wipe 前先 lint，供 inject_realm_fix_hint 使用
            volume_lint_cache: list | None = None
            if step == "volumes":
                from app.services.bootstrap.steps.volumes import run_volume_entity_lint

                ctx_pre = build_full_ctx(db, project)
                volume_lint_cache = run_volume_entity_lint(db, project_id, ctx_pre)

            # ③ 清除旧产物（同步，在协程内直接执行，db 会话独属此 stream）
            wipe_step(db, project_id, step)

            # ④ 重建 ctx
            ctx = build_full_ctx(db, project)
            if volume_lint_cache:
                ctx["volume_entity_lint"] = volume_lint_cache

            # ⑤ 初始化 GenerationService
            svc = GenerationService(
                db=db,
                model_profile=req.model_profile,
                llm_provider_id=req.llm_provider_id,
                user_id=str(current_user.id),
            )

            # ⑥ 调用对应 gen 函数
            result = await asyncio.wait_for(
                dispatch_regen(svc, project, step, ctx),
                timeout=360.0,
            )

            count = len(result) if isinstance(result, list) else (1 if result else 0)
            if count == 0 and step in ("emotion_arc", "villain_arc"):
                msg = (
                    f"{step} 生成结果为空：模型未返回有效 JSON，"
                    "或当前线路 token 不足/被拦截。请切换远程线路后重试。"
                )
                yield _sse(_emit_payload(step, "error", message=msg))
            else:
                yield _sse(_emit_payload(step, "step_done", count=count))

        except asyncio.TimeoutError:
            msg = f"{step} 重跑超时（7 分钟），请检查模型线路后重试"
            logger.error("step_regen timeout: step=%s project=%s", step, project_id)
            yield _sse(_emit_payload(step, "error", message=msg))
        except Exception as exc:
            from app.services.llm_errors import format_llm_error_message
            msg = format_llm_error_message(exc)
            logger.exception("step_regen failed: step=%s project=%s", step, project_id)
            yield _sse(_emit_payload(step, "error", message=msg))
        finally:
            yield _sse({"event": "__stream_end__"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
