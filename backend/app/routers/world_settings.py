from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import WorldSetting
from app.schemas import WorldSettingCreate, WorldSettingUpdate, WorldSettingOut

router = APIRouter(prefix="/projects/{project_id}/settings", tags=["world-settings"])


@router.get("/", response_model=List[WorldSettingOut])
def list_settings(project_id: str, db: Session = Depends(get_db)):
    return db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id
    ).order_by(WorldSetting.created_at).all()


@router.post("/", response_model=WorldSettingOut, status_code=201)
def create_setting(project_id: str, payload: WorldSettingCreate, db: Session = Depends(get_db)):
    setting = WorldSetting(project_id=project_id, **payload.model_dump())
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


@router.get("/{setting_id}", response_model=WorldSettingOut)
def get_setting(project_id: str, setting_id: str, db: Session = Depends(get_db)):
    setting = db.query(WorldSetting).filter(
        WorldSetting.id == setting_id,
        WorldSetting.project_id == project_id
    ).first()
    if not setting:
        raise HTTPException(404, "Setting not found")
    return setting


@router.patch("/{setting_id}", response_model=WorldSettingOut)
def update_setting(project_id: str, setting_id: str, payload: WorldSettingUpdate, db: Session = Depends(get_db)):
    setting = db.query(WorldSetting).filter(
        WorldSetting.id == setting_id,
        WorldSetting.project_id == project_id
    ).first()
    if not setting:
        raise HTTPException(404, "Setting not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(setting, field, value)
    db.commit()
    db.refresh(setting)
    return setting


@router.delete("/{setting_id}", status_code=204)
def delete_setting(project_id: str, setting_id: str, db: Session = Depends(get_db)):
    setting = db.query(WorldSetting).filter(
        WorldSetting.id == setting_id,
        WorldSetting.project_id == project_id
    ).first()
    if not setting:
        raise HTTPException(404, "Setting not found")
    db.delete(setting)
    db.commit()
