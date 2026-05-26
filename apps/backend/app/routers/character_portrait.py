"""
人物立绘雪碧图生成

POST /api/v1/projects/{project_id}/characters/{character_id}/portrait/generate
POST /api/v1/projects/{project_id}/characters/portraits/generate-batch
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Character
from app.models.llm_provider import LlmProvider
from app.routers.cover import CoverGenerateOut, _raw_bytes_from_generate_out
from app.routers.cover_gateway import (
    execute_images_generations,
    http_status_for_gateway_failure,
)
from app.services.character_portrait_prompt import build_character_sprite_prompt
from app.services.character_portrait_storage import save_character_sprite_sheet

router = APIRouter(tags=["character-portrait"])
logger = logging.getLogger(__name__)

DEFAULT_SPRITE_SIZE = "1792x1024"
DEFAULT_QUALITY = "standard"
SPRITE_COLS = 4
SPRITE_ROWS = 1


class CharacterPortraitGenerateIn(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    llm_provider_id: UUID
    prompt_override: Optional[str] = Field(None, description="覆盖自动拼装的 prompt")
    style_hint: Optional[str] = Field(None, description="追加风格描述，如 anime / realistic")
    size: str = DEFAULT_SPRITE_SIZE
    quality: str = DEFAULT_QUALITY


class CharacterPortraitGenerateOut(BaseModel):
    character_id: UUID
    avatar_url: str
    sprite_sheet: dict
    prompt: str


class CharacterPortraitBatchIn(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    llm_provider_id: UUID
    character_ids: List[UUID] = Field(..., min_length=1, max_length=20)
    style_hint: Optional[str] = None
    size: str = DEFAULT_SPRITE_SIZE
    quality: str = DEFAULT_QUALITY
    skip_existing: bool = Field(True, description="已有雪碧图时跳过")


class CharacterPortraitBatchItemOut(BaseModel):
    character_id: UUID
    name: str
    status: str  # ok | skipped | error
    avatar_url: Optional[str] = None
    sprite_sheet: Optional[dict] = None
    error: Optional[str] = None


class CharacterPortraitBatchOut(BaseModel):
    results: List[CharacterPortraitBatchItemOut]


def _get_image_provider(db: Session, provider_id: UUID) -> LlmProvider:
    provider = (
        db.query(LlmProvider)
        .filter(
            LlmProvider.id == provider_id,
            LlmProvider.enabled.is_(True),
            LlmProvider.provider_type == "image",
        )
        .first()
    )
    if not provider:
        raise HTTPException(404, "找不到该图片提供者，请确认已在管理后台启用并设置为 image 类型")
    return provider


def _generate_and_persist(
    db: Session,
    char: Character,
    provider: LlmProvider,
    *,
    prompt: str,
    size: str,
    quality: str,
) -> CharacterPortraitGenerateOut:
    call = execute_images_generations(
        base_url=provider.base_url,
        api_key=provider.api_key or "",
        model_name=provider.model_name,
        prompt=prompt,
        size=size,
        quality=quality,
        cover_out_cls=CoverGenerateOut,
    )
    if not call.success:
        raise HTTPException(
            http_status_for_gateway_failure(call),
            call.error_user_message or "图片生成失败",
        )

    assert call.out is not None
    try:
        blob = _raw_bytes_from_generate_out(call.out)
    except HTTPException as e:
        detail = str(e.detail) if e.detail is not None else "解析图片失败"
        raise HTTPException(502, detail) from e

    pid = str(char.project_id)
    cid = str(char.id)
    try:
        sprite_url, avatar_url, meta = save_character_sprite_sheet(
            pid, cid, blob, cols=SPRITE_COLS, rows=SPRITE_ROWS
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    now = datetime.now(timezone.utc).isoformat()
    sprite_meta = {
        **meta,
        "generated_at": now,
        "llm_provider_id": str(provider.id),
        "provider_name": provider.name,
        "model_name": provider.model_name,
        "prompt": prompt[:2000],
    }

    extra = dict(char.extra or {})
    extra["sprite_sheet"] = sprite_meta
    char.avatar_url = avatar_url
    char.extra = extra
    db.commit()
    db.refresh(char)

    return CharacterPortraitGenerateOut(
        character_id=char.id,
        avatar_url=avatar_url,
        sprite_sheet=sprite_meta,
        prompt=prompt,
    )


@router.post(
    "/projects/{project_id}/characters/{character_id}/portrait/generate",
    response_model=CharacterPortraitGenerateOut,
)
def generate_character_portrait(
    project_id: str,
    character_id: str,
    payload: CharacterPortraitGenerateIn,
    db: Session = Depends(get_db),
):
    """为单个人物生成 4 帧横排雪碧图，并写入 avatar_url 与 extra.sprite_sheet。"""
    char = (
        db.query(Character)
        .filter(Character.id == character_id, Character.project_id == project_id)
        .first()
    )
    if not char:
        raise HTTPException(404, "人物不存在")

    provider = _get_image_provider(db, payload.llm_provider_id)
    prompt = (payload.prompt_override or "").strip() or build_character_sprite_prompt(
        char, style_hint=payload.style_hint or ""
    )
    if len(prompt) < 20:
        raise HTTPException(400, "人物外貌信息过少，请先填写外貌描述或提供 prompt_override")

    return _generate_and_persist(
        db,
        char,
        provider,
        prompt=prompt,
        size=payload.size,
        quality=payload.quality,
    )


@router.post(
    "/projects/{project_id}/characters/portraits/generate-batch",
    response_model=CharacterPortraitBatchOut,
)
def generate_character_portraits_batch(
    project_id: str,
    payload: CharacterPortraitBatchIn,
    db: Session = Depends(get_db),
):
    """批量生成人物立绘（最多 20 人，逐人调用图片模型）。"""
    provider = _get_image_provider(db, payload.llm_provider_id)
    results: List[CharacterPortraitBatchItemOut] = []

    for cid in payload.character_ids:
        char = (
            db.query(Character)
            .filter(Character.id == cid, Character.project_id == project_id)
            .first()
        )
        if not char:
            results.append(
                CharacterPortraitBatchItemOut(
                    character_id=cid,
                    name="?",
                    status="error",
                    error="人物不存在",
                )
            )
            continue

        existing = (char.extra or {}).get("sprite_sheet") if isinstance(char.extra, dict) else None
        if payload.skip_existing and existing and existing.get("url"):
            results.append(
                CharacterPortraitBatchItemOut(
                    character_id=char.id,
                    name=char.name,
                    status="skipped",
                    avatar_url=char.avatar_url,
                    sprite_sheet=existing,
                )
            )
            continue

        prompt = build_character_sprite_prompt(char, style_hint=payload.style_hint or "")
        if len(prompt) < 20:
            results.append(
                CharacterPortraitBatchItemOut(
                    character_id=char.id,
                    name=char.name,
                    status="error",
                    error="外貌信息过少，已跳过",
                )
            )
            continue

        try:
            out = _generate_and_persist(
                db,
                char,
                provider,
                prompt=prompt,
                size=payload.size,
                quality=payload.quality,
            )
            results.append(
                CharacterPortraitBatchItemOut(
                    character_id=char.id,
                    name=char.name,
                    status="ok",
                    avatar_url=out.avatar_url,
                    sprite_sheet=out.sprite_sheet,
                )
            )
        except HTTPException as e:
            results.append(
                CharacterPortraitBatchItemOut(
                    character_id=char.id,
                    name=char.name,
                    status="error",
                    error=str(e.detail),
                )
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("批量立绘生成失败 character_id=%s", char.id)
            results.append(
                CharacterPortraitBatchItemOut(
                    character_id=char.id,
                    name=char.name,
                    status="error",
                    error=str(e),
                )
            )

    return CharacterPortraitBatchOut(results=results)
