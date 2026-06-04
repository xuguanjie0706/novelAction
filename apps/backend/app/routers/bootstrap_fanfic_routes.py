"""Bootstrap 同人建书辅助端点（建书前 AI 生成，非 LangGraph 步骤内）。"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.bootstrap.fanfic_canon_synopsis import gen_canon_synopsis_options
from app.services.generation_service import GenerationService

router = APIRouter(prefix="/bootstrap/fanfic", tags=["bootstrap-fanfic"])


class CanonSynopsisOptionOut(BaseModel):
    id: str
    label: str
    synopsis: str = Field(..., min_length=80)


class CanonSynopsisOptionsRequest(BaseModel):
    source_work_title: str = Field(..., min_length=1)
    logline: str = ""
    fanfic_trope: Literal["transmigration", "rebirth", "au"] = "transmigration"
    focal_characters: str = ""
    model_profile: Literal["local", "gemini"] = "gemini"
    llm_provider_id: Optional[UUID] = None

    @field_validator("source_work_title", "logline", "focal_characters", mode="before")
    @classmethod
    def _strip(cls, v: object) -> str:
        return str(v or "").strip()


class CanonSynopsisOptionsResponse(BaseModel):
    options: list[CanonSynopsisOptionOut]


@router.post(
    "/canon-synopsis-options",
    response_model=CanonSynopsisOptionsResponse,
    summary="一次生成 3 条原著梗概候选",
)
async def create_canon_synopsis_options(
    body: CanonSynopsisOptionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CanonSynopsisOptionsResponse:
    """建书前调用：根据原著名与同人创意，AI 生成 3 条梗概供用户择一。"""
    svc = GenerationService(
        db=db,
        model_profile=body.model_profile,
        llm_provider_id=body.llm_provider_id,
        user_id=current_user.id,
    )
    try:
        options = await gen_canon_synopsis_options(
            svc,
            source_work_title=body.source_work_title,
            logline=body.logline,
            fanfic_trope=body.fanfic_trope,
            focal_characters=body.focal_characters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 生成失败：{exc}") from exc

    return CanonSynopsisOptionsResponse(options=options)
