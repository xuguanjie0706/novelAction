"""
scene_stitch_routes.py — 场景缝合端点

资源边界：Scene 三层调度第三层——将 status=written 的场景正文拼接为 Chapter.content。
  POST /ai/scene-stitch
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, Project, Scene
from app.services.ai.scene_checklist import verify_scenes_after_stitch
from app.services.ai_service import AIService

router = APIRouter()
_logger = logging.getLogger(__name__)


# ── 请求 schema ─────────────────────────────────────────────────

class SceneStitchRequest(BaseModel):
    """
    场景缝合请求。

    Args:
        outline_node_id: 用于查找该节点下全部 status=written 场景。
        chapter_id: 目标章节 UUID；非空时将拼接结果写入 chapter.content。
        require_all_written: True 时若存在 planned 场景则报 400（默认 False）。
    """
    outline_node_id: UUID
    chapter_id: Optional[UUID] = None
    require_all_written: bool = False


# ── 端点：场景缝合 → chapter.content ────────────────────────────

@router.post("/scene-stitch")
async def scene_stitch(
    project_id: str,
    req: SceneStitchRequest,
    db: Session = Depends(get_db),
):
    """
    场景缝合（三层调度第三层）。

    按 ``order`` 升序拼接同 ``outline_node_id`` 下所有 ``status=written``
    的场景正文，写入目标 Chapter.content 作为可编辑草稿。

    Returns:
        {"word_count": N, "scene_count": N, "chapter_id": str|null,
         "content_preview": str（前200字）}

    Raises:
        404: outline_node / chapter 不存在。
        400: require_all_written=True 且存在未完成场景。
        422: 无 written 场景可缝合。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    scenes: list[Scene] = (
        db.query(Scene)
        .filter(
            Scene.project_id == project_id,
            Scene.outline_node_id == req.outline_node_id,
        )
        .order_by(Scene.order.asc())
        .all()
    )
    if not scenes:
        raise HTTPException(422, "No scenes found for this outline_node_id")

    if req.require_all_written:
        unwritten = [s for s in scenes if s.status != "written"]
        if unwritten:
            raise HTTPException(
                400,
                f"{len(unwritten)} scene(s) not yet written: "
                + ", ".join(str(s.id) for s in unwritten),
            )

    written = [s for s in scenes if s.status == "written" and s.content]
    if not written:
        raise HTTPException(422, "No written scenes to stitch")

    stitched = "\n\n".join(s.content for s in written)

    chapter_id_str: Optional[str] = None
    if req.chapter_id:
        chapter = db.query(Chapter).filter(
            Chapter.id == req.chapter_id,
            Chapter.project_id == project_id,
        ).first()
        if not chapter:
            raise HTTPException(404, "Chapter not found")
        chapter.content = stitched
        chapter_id_str = str(chapter.id)

        # 绑定 scene.chapter_id
        for s in written:
            if s.chapter_id is None:
                s.chapter_id = req.chapter_id

        db.commit()

    # 异步触发场景核验（不阻塞 stitch 响应）
    svc_for_check = AIService("default", db=db)

    async def _run_checklist():
        try:
            await verify_scenes_after_stitch(
                db=db,
                project_id=project_id,
                outline_node_id=str(req.outline_node_id),
                svc=svc_for_check,
            )
        except Exception as exc:
            _logger.warning("verify_scenes_after_stitch failed: %s", exc)

    asyncio.create_task(_run_checklist())

    return {
        "word_count": len(stitched),
        "scene_count": len(written),
        "chapter_id": chapter_id_str,
        "content_preview": stitched[:200],
    }
