from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import Foreshadow
from app.schemas import ForeshadowCreate, ForeshadowUpdate, ForeshadowOut

router = APIRouter(prefix="/projects/{project_id}/foreshadows", tags=["foreshadows"])


def _auto_code(db: Session, project_id: str) -> str:
    """生成自增编号，如 F-001, F-002 …"""
    count = db.query(Foreshadow).filter(
        Foreshadow.project_id == project_id
    ).count()
    return f"F-{count + 1:03d}"


@router.get("/", response_model=List[ForeshadowOut])
def list_foreshadows(
    project_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
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
