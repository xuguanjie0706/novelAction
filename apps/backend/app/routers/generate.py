from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Literal, Optional
from sqlalchemy.orm import Session
from uuid import UUID

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.generation_service import GenerationService

router = APIRouter(prefix="/bootstrap", tags=["bootstrap"])


class BootstrapRequest(BaseModel):
    logline: str
    premise: Optional[str] = None
    mode: Literal["sequential", "single_shot"] = "single_shot"
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None
    target_words: int = 1_200_000  # 全书目标字数，驱动卷章结构规划


@router.post("/stream")
async def bootstrap_stream(
    req: BootstrapRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    一句话创意 → 全量初始化小说（SSE 流式推送进度）

    model_profile / llm_provider_id 决定实际调用的线路；与 mode 无关。

    mode="single_shot"（默认）单次大 JSON，适合远程大上下文。
    mode="sequential" 多步串行，同样完全遵循请求中的线路选择（兼容回退）。

    新建的 Project 会自动绑定到 current_user，确保多用户隔离。
    """
    svc = GenerationService(
        db=db,
        model_profile=req.model_profile,
        llm_provider_id=req.llm_provider_id,
        user_id=current_user.id,
    )

    async def event_stream():
        async for chunk in svc.bootstrap(
            logline=req.logline,
            premise=req.premise or "",
            mode=req.mode,
            target_words=req.target_words,
        ):
            yield chunk
        # 心跳结束
        yield "data: {\"event\": \"end\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # 关闭 nginx 缓冲，SSE 即时推送
        },
    )
