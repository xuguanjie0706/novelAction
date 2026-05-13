"""
Scenes Router — 章节分场 CRUD

端点列表：
  GET    /projects/{pid}/scenes/         列出分场（按 outline_node_id 或 chapter_id 过滤）
  GET    /projects/{pid}/scenes/{id}     单场详情
  POST   /projects/{pid}/scenes/         创建单场
  POST   /projects/{pid}/scenes/batch    批量创建（支持先清空旧场景，供 AI 生成后入库使用）
  PATCH  /projects/{pid}/scenes/{id}     更新单场
  DELETE /projects/{pid}/scenes/{id}     删除单场
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import Scene, Project
from app.schemas import SceneCreate, SceneUpdate, SceneRead

router = APIRouter(prefix="/projects/{project_id}/scenes", tags=["scenes"])


# ── 批量创建请求体 ─────────────────────────────────────────

class SceneBatchCreate(BaseModel):
    """
    批量入库分场列表，通常由 /ai/scene-plan 生成后直接提交。

    Args:
        scenes: 分场数据列表，按 order 顺序排列。
        outline_node_id: 所属 chapter_plan 节点 ID；若提供，
            每条 scene 缺省时自动填入此值。
        replace_existing: 是否先删除同 outline_node_id 的旧场景
            再写入（默认 True，确保幂等）。
    """
    scenes: List[SceneCreate]
    outline_node_id: Optional[str] = None
    replace_existing: bool = True


# ── 端点 ──────────────────────────────────────────────────

@router.get("/", response_model=List[SceneRead])
def list_scenes(
    project_id: str,
    db: Session = Depends(get_db),
    outline_node_id: Optional[str] = None,
    chapter_id: Optional[str] = None,
):
    """
    列出项目内的分场记录，按 order 升序。
    可同时或单独按 outline_node_id / chapter_id 过滤。
    """
    q = db.query(Scene).filter(Scene.project_id == project_id)
    if outline_node_id:
        q = q.filter(Scene.outline_node_id == outline_node_id)
    if chapter_id:
        q = q.filter(Scene.chapter_id == chapter_id)
    return q.order_by(Scene.order.asc()).all()


@router.get("/{scene_id}", response_model=SceneRead)
def get_scene(project_id: str, scene_id: str, db: Session = Depends(get_db)):
    """获取单条分场详情。"""
    scene = db.query(Scene).filter(
        Scene.id == scene_id, Scene.project_id == project_id
    ).first()
    if not scene:
        raise HTTPException(404, "Scene not found")
    return scene


@router.post("/", response_model=SceneRead, status_code=201)
def create_scene(project_id: str, payload: SceneCreate, db: Session = Depends(get_db)):
    """创建单条分场记录。"""
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(404, "Project not found")
    scene = Scene(project_id=project_id, **payload.dict(exclude_unset=True))
    db.add(scene)
    db.commit()
    db.refresh(scene)
    return scene


@router.post("/batch", response_model=List[SceneRead], status_code=201)
def batch_create_scenes(
    project_id: str,
    payload: SceneBatchCreate,
    db: Session = Depends(get_db),
):
    """
    批量创建分场——通常由前端在 AI 生成分场计划后调用。

    若 replace_existing=True 且提供了 outline_node_id，
    会先删除该节点下的所有旧场景，再写入新场景，保证幂等。

    Args:
        payload.scenes: 分场列表，每条可单独指定 outline_node_id。
        payload.outline_node_id: 批次级节点 ID，scene 缺省时自动填入。
        payload.replace_existing: 是否清空旧场景（默认 True）。

    Returns:
        新创建的 SceneRead 列表，按 order 升序。
    """
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(404, "Project not found")

    # 清空旧场景
    if payload.replace_existing and payload.outline_node_id:
        db.query(Scene).filter(
            Scene.project_id == project_id,
            Scene.outline_node_id == payload.outline_node_id,
        ).delete(synchronize_session=False)

    created: List[Scene] = []
    for sc_data in payload.scenes:
        data = sc_data.dict(exclude_unset=True)
        # 批次级 outline_node_id 作为默认值
        if payload.outline_node_id and not data.get("outline_node_id"):
            data["outline_node_id"] = payload.outline_node_id
        scene = Scene(project_id=project_id, **data)
        db.add(scene)
        created.append(scene)

    db.commit()
    for s in created:
        db.refresh(s)

    return sorted(created, key=lambda s: s.order)


@router.patch("/{scene_id}", response_model=SceneRead)
def update_scene(
    project_id: str,
    scene_id: str,
    payload: SceneUpdate,
    db: Session = Depends(get_db),
):
    """更新单条分场字段（部分更新）。"""
    scene = db.query(Scene).filter(
        Scene.id == scene_id, Scene.project_id == project_id
    ).first()
    if not scene:
        raise HTTPException(404, "Scene not found")
    for k, v in payload.dict(exclude_unset=True).items():
        setattr(scene, k, v)
    db.commit()
    db.refresh(scene)
    return scene


@router.delete("/{scene_id}")
def delete_scene(project_id: str, scene_id: str, db: Session = Depends(get_db)):
    """删除单条分场记录。"""
    scene = db.query(Scene).filter(
        Scene.id == scene_id, Scene.project_id == project_id
    ).first()
    if not scene:
        raise HTTPException(404, "Scene not found")
    db.delete(scene)
    db.commit()
    return {"ok": True}
