from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.database import get_db
from app.models import StoryLine
from app.schemas.storyline import StoryLineCreate, StoryLineUpdate, StoryLineOut
from app.services.ai.storyline_drift import build_weave_matrix_overview

router = APIRouter(prefix="/projects/{project_id}/storylines", tags=["故事线"])


@router.get("/weave-matrix")
def get_storyline_weave_matrix(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """故事线 × 卷织网矩阵（计划张力 + 复盘实际值 + 漂移警报）。"""
    return build_weave_matrix_overview(db, str(project_id))


@router.get("/", response_model=List[StoryLineOut])
def list_storylines(project_id: uuid.UUID, db: Session = Depends(get_db)):
    return db.query(StoryLine).filter(
        StoryLine.project_id == project_id
    ).order_by(StoryLine.sort_order, StoryLine.created_at).all()


@router.post("/", response_model=StoryLineOut)
def create_storyline(project_id: uuid.UUID, data: StoryLineCreate, db: Session = Depends(get_db)):
    obj = StoryLine(project_id=project_id, **data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{storyline_id}", response_model=StoryLineOut)
def get_storyline(project_id: uuid.UUID, storyline_id: uuid.UUID, db: Session = Depends(get_db)):
    obj = db.query(StoryLine).filter(
        StoryLine.id == storyline_id, StoryLine.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="StoryLine not found")
    return obj


@router.patch("/{storyline_id}", response_model=StoryLineOut)
def update_storyline(
    project_id: uuid.UUID, storyline_id: uuid.UUID,
    data: StoryLineUpdate, db: Session = Depends(get_db)
):
    obj = db.query(StoryLine).filter(
        StoryLine.id == storyline_id, StoryLine.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="StoryLine not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{storyline_id}")
def delete_storyline(project_id: uuid.UUID, storyline_id: uuid.UUID, db: Session = Depends(get_db)):
    obj = db.query(StoryLine).filter(
        StoryLine.id == storyline_id, StoryLine.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="StoryLine not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
