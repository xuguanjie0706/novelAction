from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.database import get_db
from app.models import Scene, Project
from app.schemas import SceneCreate, SceneUpdate, SceneRead

router = APIRouter(prefix="/projects/{project_id}/scenes", tags=["scenes"])


@router.get("/", response_model=List[SceneRead])
def list_scenes(project_id: str, db: Session = Depends(get_db), outline_node_id: Optional[str] = None, chapter_id: Optional[str] = None):
    q = db.query(Scene).filter(Scene.project_id == project_id)
    if outline_node_id:
        q = q.filter(Scene.outline_node_id == outline_node_id)
    if chapter_id:
        q = q.filter(Scene.chapter_id == chapter_id)
    return q.order_by(Scene.order.asc()).all()


@router.get("/{scene_id}", response_model=SceneRead)
def get_scene(project_id: str, scene_id: str, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id, Scene.project_id == project_id).first()
    if not scene:
        raise HTTPException(404, "Scene not found")
    return scene


@router.post("/", response_model=SceneRead)
def create_scene(project_id: str, payload: SceneCreate, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(404, "Project not found")
    scene = Scene(
        project_id=project_id,
        **payload.dict(exclude_unset=True)
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)
    return scene


@router.patch("/{scene_id}", response_model=SceneRead)
def update_scene(project_id: str, scene_id: str, payload: SceneUpdate, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id, Scene.project_id == project_id).first()
    if not scene:
        raise HTTPException(404, "Scene not found")
    for k, v in payload.dict(exclude_unset=True).items():
        setattr(scene, k, v)
    db.commit()
    db.refresh(scene)
    return scene


@router.delete("/{scene_id}")
def delete_scene(project_id: str, scene_id: str, db: Session = Depends(get_db)):
    scene = db.query(Scene).filter(Scene.id == scene_id, Scene.project_id == project_id).first()
    if not scene:
        raise HTTPException(404, "Scene not found")
    db.delete(scene)
    db.commit()
    return {"ok": True}
