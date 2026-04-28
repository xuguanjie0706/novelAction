from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LlmProvider
from app.schemas.llm_provider import (
    LlmProviderCreate,
    LlmProviderUpdate,
    LlmProviderOut,
    mask_api_key_hint,
)
from app.services.llm_config import clear_other_defaults

router = APIRouter(prefix="/admin/llm-providers", tags=["admin-llm"])


def _to_out(row: LlmProvider) -> LlmProviderOut:
    has_k, hint = mask_api_key_hint(row.api_key)
    return LlmProviderOut(
        id=row.id,
        name=row.name,
        base_url=row.base_url,
        model_name=row.model_name,
        has_api_key=has_k,
        api_key_hint=hint,
        enabled=row.enabled,
        is_default=row.is_default,
        sort_order=row.sort_order,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/", response_model=List[LlmProviderOut])
def list_providers(db: Session = Depends(get_db)):
    rows = db.query(LlmProvider).order_by(LlmProvider.sort_order.asc(), LlmProvider.created_at.asc()).all()
    return [_to_out(r) for r in rows]


@router.post("/", response_model=LlmProviderOut, status_code=201)
def create_provider(payload: LlmProviderCreate, db: Session = Depends(get_db)):
    row = LlmProvider(
        name=payload.name.strip(),
        base_url=payload.base_url.strip(),
        model_name=payload.model_name.strip(),
        api_key=(payload.api_key.strip() if payload.api_key else None),
        enabled=payload.enabled,
        is_default=payload.is_default,
        sort_order=payload.sort_order,
    )
    db.add(row)
    db.flush()
    if row.is_default:
        clear_other_defaults(db, row.id)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.patch("/{provider_id}", response_model=LlmProviderOut)
def update_provider(provider_id: UUID, payload: LlmProviderUpdate, db: Session = Depends(get_db)):
    row = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
    if not row:
        raise HTTPException(404, "大模型配置不存在")
    data = payload.model_dump(exclude_unset=True)
    if "api_key" in data:
        ak = data.pop("api_key")
        if ak == "":
            row.api_key = None
        elif ak is not None:
            row.api_key = ak.strip()
    for k, v in data.items():
        if v is None and k in ("name", "base_url", "model_name"):
            continue
        if k in ("name", "base_url", "model_name") and isinstance(v, str):
            v = v.strip()
        setattr(row, k, v)
    db.flush()
    if row.is_default:
        clear_other_defaults(db, row.id)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: UUID, db: Session = Depends(get_db)):
    row = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
    if not row:
        raise HTTPException(404, "大模型配置不存在")
    db.delete(row)
    db.commit()


@router.post("/{provider_id}/set-default", response_model=LlmProviderOut)
def set_default_provider(provider_id: UUID, db: Session = Depends(get_db)):
    row = db.query(LlmProvider).filter(LlmProvider.id == provider_id).first()
    if not row:
        raise HTTPException(404, "大模型配置不存在")
    row.is_default = True
    row.enabled = True
    clear_other_defaults(db, row.id)
    db.commit()
    db.refresh(row)
    return _to_out(row)
