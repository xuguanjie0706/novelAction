from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import re

from app.database import get_db
from app.models import Foreshadow
from app.schemas import ForeshadowCreate, ForeshadowUpdate, ForeshadowOut

router = APIRouter(prefix="/projects/{project_id}/foreshadows", tags=["foreshadows"])


def _code_number(code: str | None) -> Optional[int]:
    if not code:
        return None
    match = re.search(r"\bF[-_ ]?(\d{1,4})\b", code, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _existing_codes(db: Session, project_id: str) -> set[str]:
    rows = db.query(Foreshadow.code).filter(
        Foreshadow.project_id == project_id
    ).all()
    codes = set()
    for row in rows:
        try:
            raw_code = row[0]
        except Exception:
            raw_code = row
        if raw_code:
            codes.add(str(raw_code).strip())
    return codes


def _next_available_code(used_codes: set[str]) -> str:
    max_number = 0
    for code in used_codes:
        number = _code_number(code)
        if number is not None:
            max_number = max(max_number, number)
    next_number = max_number + 1
    while f"F-{next_number:03d}" in used_codes:
        next_number += 1
    code = f"F-{next_number:03d}"
    used_codes.add(code)
    return code


def _auto_code(db: Session, project_id: str) -> str:
    """生成自增编号，如 F-001, F-002 …"""
    return _next_available_code(_existing_codes(db, project_id))


def _repair_duplicate_codes(db: Session, project_id: str) -> None:
    items = db.query(Foreshadow).filter(
        Foreshadow.project_id == project_id
    ).order_by(Foreshadow.created_at, Foreshadow.id).all()
    used_codes: set[str] = set()
    changed = False
    for item in items:
        code = (item.code or "").strip()
        if code and code not in used_codes:
            item.code = code
            used_codes.add(code)
            continue
        item.code = _next_available_code(used_codes)
        changed = True
    if changed:
        db.commit()


@router.get("/", response_model=List[ForeshadowOut])
def list_foreshadows(
    project_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    _repair_duplicate_codes(db, project_id)
    q = db.query(Foreshadow).filter(Foreshadow.project_id == project_id)
    if status:
        q = q.filter(Foreshadow.status == status)
    return q.order_by(Foreshadow.priority.desc(), Foreshadow.created_at).all()


@router.post("/", response_model=ForeshadowOut, status_code=201)
def create_foreshadow(
    project_id: str,
    payload: ForeshadowCreate,
    db: Session = Depends(get_db),
):
    data = payload.model_dump()
    data["project_id"] = project_id
    if not data.get("code"):
        data["code"] = _auto_code(db, project_id)
    obj = Foreshadow(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{foreshadow_id}", response_model=ForeshadowOut)
def get_foreshadow(
    project_id: str,
    foreshadow_id: str,
    db: Session = Depends(get_db),
):
    obj = db.query(Foreshadow).filter(
        Foreshadow.id == foreshadow_id,
        Foreshadow.project_id == project_id,
    ).first()
    if not obj:
        raise HTTPException(404, "Foreshadow not found")
    return obj


@router.patch("/{foreshadow_id}", response_model=ForeshadowOut)
def update_foreshadow(
    project_id: str,
    foreshadow_id: str,
    payload: ForeshadowUpdate,
    db: Session = Depends(get_db),
):
    obj = db.query(Foreshadow).filter(
        Foreshadow.id == foreshadow_id,
        Foreshadow.project_id == project_id,
    ).first()
    if not obj:
        raise HTTPException(404, "Foreshadow not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{foreshadow_id}", status_code=204)
def delete_foreshadow(
    project_id: str,
    foreshadow_id: str,
    db: Session = Depends(get_db),
):
    obj = db.query(Foreshadow).filter(
        Foreshadow.id == foreshadow_id,
        Foreshadow.project_id == project_id,
    ).first()
    if not obj:
        raise HTTPException(404, "Foreshadow not found")
    db.delete(obj)
    db.commit()
