import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

from app.database import get_db
from app.models import Faction
from app.schemas.faction import FactionCreate, FactionUpdate, FactionOut

router = APIRouter(prefix="/projects/{project_id}/factions", tags=["势力组织"])

_FACTION_LOCATION_MARKERS = ("郡", "州", "府", "城", "县", "镇", "村", "域", "界", "岭", "谷", "海", "湖")


def _normalize_faction_name_candidates(name: Optional[str]) -> set[str]:
    text = (name or "").strip()
    if not text:
        return set()
    compact = re.sub(r"[\s·•\\\-_/（）()【】\[\]<>《》“”\"'`~!@#$%^&*+,，。；：、？?]+", "", text)
    if not compact:
        return set()
    candidates = {compact}
    for marker in _FACTION_LOCATION_MARKERS:
        if marker in compact:
            tail = compact.rsplit(marker, 1)[-1]
            if len(tail) >= 2:
                candidates.add(tail)
    if "的" in compact:
        tail = compact.rsplit("的", 1)[-1]
        if len(tail) >= 2:
            candidates.add(tail)
    return candidates


def _append_alias(faction: Faction, alias_name: str) -> None:
    alias = (alias_name or "").strip()
    if not alias or alias == faction.name:
        return
    extra = dict(faction.extra or {})
    aliases = [str(v).strip() for v in (extra.get("name_aliases") or []) if str(v).strip()]
    if alias not in aliases:
        aliases.append(alias)
    extra["name_aliases"] = aliases
    faction.extra = extra


def _find_existing_faction(db: Session, project_id: uuid.UUID, name: str) -> Optional[Faction]:
    exact = db.query(Faction).filter(Faction.project_id == project_id, Faction.name == name).first()
    if exact:
        return exact
    lookup = _normalize_faction_name_candidates(name)
    if not lookup:
        return None
    factions = db.query(Faction).filter(Faction.project_id == project_id).all()
    for faction in factions:
        candidates = _normalize_faction_name_candidates(faction.name)
        extra = dict(faction.extra or {})
        for alias in (extra.get("name_aliases") or []):
            candidates |= _normalize_faction_name_candidates(str(alias))
        if lookup & candidates:
            return faction
    return None


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
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Faction name is required")

    existed = _find_existing_faction(db, project_id, name)
    if existed:
        _append_alias(existed, name)
        db.commit()
        db.refresh(existed)
        return existed

    payload = data.model_dump()
    payload["name"] = name
    obj = Faction(project_id=project_id, **payload)
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
