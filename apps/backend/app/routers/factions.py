from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

from app.database import get_db
from app.models import Faction
from app.schemas.faction import FactionCreate, FactionUpdate, FactionOut

router = APIRouter(prefix="/projects/{project_id}/factions", tags=["势力组织"])


@router.get("/", response_model=List[FactionOut])
def list_factions(
    project_id: uuid.UUID,
    faction_type: Optional[str] = None,
    alignment: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(Faction).filter(Faction.project_id == project_id)
    if faction_type:
        q = q.filter(Faction.faction_type == faction_type)
    if alignment:
        q = q.filter(Faction.alignment == alignment)
    return q.order_by(Faction.sort_order, Faction.created_at).all()


@router.post("/", response_model=FactionOut)
def create_faction(project_id: uuid.UUID, data: FactionCreate, db: Session = Depends(get_db)):
    obj = Faction(project_id=project_id, **data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{faction_id}", response_model=FactionOut)
def get_faction(project_id: uuid.UUID, faction_id: uuid.UUID, db: Session = Depends(get_db)):
    obj = db.query(Faction).filter(
        Faction.id == faction_id, Faction.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Faction not found")
    return obj


@router.patch("/{faction_id}", response_model=FactionOut)
def update_faction(
    project_id: uuid.UUID, faction_id: uuid.UUID,
    data: FactionUpdate, db: Session = Depends(get_db)
):
    obj = db.query(Faction).filter(
        Faction.id == faction_id, Faction.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Faction not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{faction_id}")
def delete_faction(project_id: uuid.UUID, faction_id: uuid.UUID, db: Session = Depends(get_db)):
    obj = db.query(Faction).filter(
        Faction.id == faction_id, Faction.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Faction not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
