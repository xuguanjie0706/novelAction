from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

from app.database import get_db
from app.models import Item
from app.schemas.item import ItemCreate, ItemUpdate, ItemOut

router = APIRouter(prefix="/projects/{project_id}/items", tags=["道具法宝"])


@router.get("/", response_model=List[ItemOut])
def list_items(
    project_id: uuid.UUID,
    item_type: Optional[str] = None,
    rarity: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(Item).filter(Item.project_id == project_id)
    if item_type:
        q = q.filter(Item.item_type == item_type)
    if rarity:
        q = q.filter(Item.rarity == rarity)
    return q.order_by(Item.sort_order, Item.created_at).all()


@router.post("/", response_model=ItemOut)
def create_item(project_id: uuid.UUID, data: ItemCreate, db: Session = Depends(get_db)):
    obj = Item(project_id=project_id, **data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{item_id}", response_model=ItemOut)
def get_item(project_id: uuid.UUID, item_id: uuid.UUID, db: Session = Depends(get_db)):
    obj = db.query(Item).filter(
        Item.id == item_id, Item.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Item not found")
    return obj


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(
    project_id: uuid.UUID, item_id: uuid.UUID,
    data: ItemUpdate, db: Session = Depends(get_db)
):
    obj = db.query(Item).filter(
        Item.id == item_id, Item.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Item not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{item_id}")
def delete_item(project_id: uuid.UUID, item_id: uuid.UUID, db: Session = Depends(get_db)):
    obj = db.query(Item).filter(
        Item.id == item_id, Item.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
