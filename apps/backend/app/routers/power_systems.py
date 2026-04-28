from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.database import get_db
from app.models import PowerSystem
from app.schemas.power_system import PowerSystemCreate, PowerSystemUpdate, PowerSystemOut

router = APIRouter(prefix="/projects/{project_id}/power-systems", tags=["境界体系"])


@router.get("/", response_model=List[PowerSystemOut])
def list_power_systems(project_id: uuid.UUID, db: Session = Depends(get_db)):
    return db.query(PowerSystem).filter(
        PowerSystem.project_id == project_id
    ).order_by(PowerSystem.sort_order, PowerSystem.created_at).all()


@router.post("/", response_model=PowerSystemOut)
def create_power_system(project_id: uuid.UUID, data: PowerSystemCreate, db: Session = Depends(get_db)):
    obj = PowerSystem(project_id=project_id, **data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{system_id}", response_model=PowerSystemOut)
def get_power_system(project_id: uuid.UUID, system_id: uuid.UUID, db: Session = Depends(get_db)):
    obj = db.query(PowerSystem).filter(
        PowerSystem.id == system_id, PowerSystem.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="PowerSystem not found")
    return obj


@router.patch("/{system_id}", response_model=PowerSystemOut)
def update_power_system(
    project_id: uuid.UUID, system_id: uuid.UUID,
    data: PowerSystemUpdate, db: Session = Depends(get_db)
):
    obj = db.query(PowerSystem).filter(
        PowerSystem.id == system_id, PowerSystem.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="PowerSystem not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{system_id}")
def delete_power_system(project_id: uuid.UUID, system_id: uuid.UUID, db: Session = Depends(get_db)):
    obj = db.query(PowerSystem).filter(
        PowerSystem.id == system_id, PowerSystem.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="PowerSystem not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
