from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

from app.database import get_db
from app.models import Skill
from app.schemas.skill import SkillCreate, SkillUpdate, SkillOut

router = APIRouter(prefix="/projects/{project_id}/skills", tags=["功法技能"])


@router.get("/", response_model=List[SkillOut])
def list_skills(
    project_id: uuid.UUID,
    skill_type: Optional[str] = None,
    grade: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(Skill).filter(Skill.project_id == project_id)
    if skill_type:
        q = q.filter(Skill.skill_type == skill_type)
    if grade:
        q = q.filter(Skill.grade == grade)
    return q.order_by(Skill.sort_order, Skill.created_at).all()


@router.post("/", response_model=SkillOut)
def create_skill(project_id: uuid.UUID, data: SkillCreate, db: Session = Depends(get_db)):
    obj = Skill(project_id=project_id, **data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{skill_id}", response_model=SkillOut)
def get_skill(project_id: uuid.UUID, skill_id: uuid.UUID, db: Session = Depends(get_db)):
    obj = db.query(Skill).filter(
        Skill.id == skill_id, Skill.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Skill not found")
    return obj


@router.patch("/{skill_id}", response_model=SkillOut)
def update_skill(
    project_id: uuid.UUID, skill_id: uuid.UUID,
    data: SkillUpdate, db: Session = Depends(get_db)
):
    obj = db.query(Skill).filter(
        Skill.id == skill_id, Skill.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Skill not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{skill_id}")
def delete_skill(project_id: uuid.UUID, skill_id: uuid.UUID, db: Session = Depends(get_db)):
    obj = db.query(Skill).filter(
        Skill.id == skill_id, Skill.project_id == project_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Skill not found")
    db.delete(obj)
    db.commit()
    return {"ok": True}
