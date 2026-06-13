"""dabai 实验书架 — 按卷展开章纲路由（写作期，bootstrap 之后）。

资源边界：仅本端点一个动词 —— 把 DabaiVolume 卷骨架懒展开为 DabaiChapterOutline 章纲。
业务实现在 services/dabai/volume_expand.py，本文件只做参数解析 + SSE 薄壳。

POST /api/v1/dabai/projects/{project_id}/volumes/{volume_id}/expand-chapters（SSE）
  事件：expand_start → chapter_batch×N → done | error
  语义：未满卷增量补全；满卷需 force=true 删旧重做（同番茄线约定）。
"""

from __future__ import annotations

import logging
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.dabai import DabaiVolume
from app.models.user import User
from app.routers.dabai import _owned_or_404, _resolve_connection, _sse
from app.services.dabai.volume_expand import VolumeAlreadyFull, aiter_volume_expand

logger = logging.getLogger("dabai.expand")

router = APIRouter(prefix="/dabai", tags=["dabai"])


class ExpandRequest(BaseModel):
    """卷展开请求。"""

    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None
    force: bool = Field(default=False, description="满卷时删旧重做")
    chapter_batch_size: Optional[int] = Field(default=None, ge=5, le=60)
    outline_expand_size: Optional[int] = Field(default=None, ge=5, le=60)


def _expand_cfg(project, req: ExpandRequest, db: Session):
    """从项目 meta 重建 DabaiConfig（批大小可被请求覆写）。"""
    from dabai.config import DabaiConfig

    meta = project.meta or {}
    cfg = DabaiConfig(
        logline=project.logline,
        volume_count=int(meta.get("volume_count", 6)),
        volume_chapters=int(meta.get("volume_chapters", 30)),
        outline_expand_size=int(req.outline_expand_size
                                or meta.get("outline_expand_size", 15)),
        chapter_batch_size=int(req.chapter_batch_size
                               or meta.get("chapter_batch_size", 5)),
    )
    cfg.base_url, cfg.api_key, cfg.model = _resolve_connection(
        db, req.model_profile, req.llm_provider_id,
    )
    return cfg


def _expand_call(cfg, req: ExpandRequest, db: Session, user: User):
    """构造注入式调用器（AIService._call_ai）。"""
    from dabai.llm_client import parse_json
    from app.services.ai.service import AIService
    ai = AIService(profile=req.model_profile, db=db,
                   llm_provider_id=req.llm_provider_id, user_id=user.id)
    heavy_steps = {"volume_chapters", "chapter_outlines", "beat_sequence", "chapter_repair"}

    async def call(step: str, system: str, user_prompt: str, meta: dict | None):
        max_tokens = cfg.max_tokens if step in heavy_steps else None
        text = await ai._call_ai(
            system, user_prompt, max_tokens=max_tokens, task=f"dabai.{step}",
        )
        return parse_json(text)

    return call


@router.post("/projects/{project_id}/volumes/{volume_id}/expand-chapters")
async def expand_volume_chapters(
    project_id: UUID,
    volume_id: UUID,
    req: ExpandRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """按卷懒展开章纲（SSE，边生成边落库，中断不丢已生成批次）。"""
    project = _owned_or_404(db, project_id, user)
    volume = (
        db.query(DabaiVolume)
        .filter(DabaiVolume.id == volume_id, DabaiVolume.project_id == project.id)
        .first()
    )
    if not volume:
        raise HTTPException(status_code=404, detail="目标卷不存在")

    cfg = _expand_cfg(project, req, db)
    call = _expand_call(cfg, req, db, user)

    async def event_gen():
        try:
            async for ev in aiter_volume_expand(
                db, project, volume, cfg, call, force=req.force,
            ):
                yield _sse(ev)
        except VolumeAlreadyFull as exc:
            yield _sse({"event": "error", "code": "volume_full", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.error("dabai 卷展开异常 project=%s vol=%s：%s",
                         project_id, volume_id, exc)
            yield _sse({"event": "error", "message": str(exc)})

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})
