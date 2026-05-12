"""
已有项目：AI 一键生成 / 补全 / 追加世界观设定卡（WorldSetting）。

与 Bootstrap Step8 共用 ``GenerationService`` 内逻辑，便于测试与迭代 prompt。
"""
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.routers.projects import _owned_or_404
from app.schemas import WorldSettingOut
from app.services.generation_service import GenerationService

router = APIRouter(prefix="/world-settings", tags=["ai-world-settings"])


class WorldSettingsGenerateRequest(BaseModel):
    """世界观设定卡 AI 生成请求体。"""

    mode: Literal["blueprint_replace", "blueprint_fill_missing", "append"]
    user_hint: str = ""
    append_count: int = Field(default=6, ge=3, le=12)
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None


class WorldSettingsGenerateResponse(BaseModel):
    """返回新写入的设定卡列表（含 id），供前端 upsert 到 store。"""

    mode: str
    created_count: int
    message: Optional[str] = None
    settings: List[WorldSettingOut]


@router.post("/generate", response_model=WorldSettingsGenerateResponse)
async def generate_world_settings(
    project_id: str,
    body: WorldSettingsGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    按模式生成并持久化 ``WorldSetting`` 记录。

    - ``blueprint_replace``：删除本项目全部设定卡后，按标准蓝图整套重建（测试常用）。
    - ``blueprint_fill_missing``：仅生成标题尚未出现的蓝图卡。
    - ``append``：在保留旧卡前提下追加若干张自拟标题卡；``user_hint`` 描述追加方向。
    """
    project = _owned_or_404(db, project_id, current_user)
    svc = GenerationService(
        db=db,
        model_profile=body.model_profile,
        llm_provider_id=body.llm_provider_id,
        user_id=current_user.id,
    )
    try:
        result = await svc.regenerate_world_settings(
            project,
            mode=body.mode,
            user_hint=body.user_hint,
            append_count=body.append_count,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 生成失败：{e}") from e

    rows = result.get("settings") or []
    settings_out = [WorldSettingOut.model_validate(s) for s in rows]
    return WorldSettingsGenerateResponse(
        mode=result["mode"],
        created_count=int(result.get("created_count") or 0),
        message=result.get("message"),
        settings=settings_out,
    )
