from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Literal
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.generation_service import GenerationService

router = APIRouter(prefix="/bootstrap", tags=["bootstrap"])


class BootstrapRequest(BaseModel):
    logline: str
    mode: Literal["sequential", "single_shot"] = "sequential"


@router.post("/stream")
async def bootstrap_stream(
    req: BootstrapRequest,
    db: Session = Depends(get_db),
):
    """
    一句话创意 → 全量初始化小说（SSE 流式推送进度）

    mode="sequential"  适合 qwen3:8b 等小模型（默认）
    mode="single_shot" 适合 Gemini / GPT-4o 等大 context 模型
    """
    svc = GenerationService(db=db)

    async def event_stream():
        async for chunk in svc.bootstrap(logline=req.logline, mode=req.mode):
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
