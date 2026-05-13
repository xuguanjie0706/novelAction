"""
locations.py — 地点（Location）CRUD 路由

资源边界：
  - 本模块只负责地点的增删改查；
  - 写章时的空间约束注入由 routers/ai/gated_draft_routes._build_location_context 负责；
  - 不处理章节或 Scene 与 Location 的关联——由 Scene CRUD 自行维护 location_id。

端点前缀由 main.py 注册：/api/v1/projects/{project_id}/locations
"""

from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.location import Location
from app.schemas.location import LocationCreate, LocationOut, LocationUpdate

router = APIRouter(
    prefix="/projects/{project_id}/locations",
    tags=["locations"],
)


def _get_or_404(db: Session, project_id: str, location_id: UUID) -> Location:
    """按项目+主键查地点，不存在则 404。"""
    loc = (
        db.query(Location)
        .filter(Location.id == location_id, Location.project_id == project_id)
        .first()
    )
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")
    return loc


@router.get("", response_model=List[LocationOut])
def list_locations(
    project_id: str,
    db: Session = Depends(get_db),
):
    """列出项目所有地点，按 sort_order 升序、name 升序排列。"""
    return (
        db.query(Location)
        .filter(Location.project_id == project_id)
        .order_by(Location.sort_order.asc(), Location.name.asc())
        .all()
    )


@router.post("", response_model=LocationOut, status_code=201)
def create_location(
    project_id: str,
    payload: LocationCreate,
    db: Session = Depends(get_db),
):
    """创建新地点。

    Args:
        project_id: 项目 UUID（来自路径）
        payload: 地点创建请求体
        db: 数据库 Session

    Returns:
        LocationOut: 新创建的地点记录
    """
    loc = Location(
        project_id=project_id,
        **payload.dict(exclude_unset=False),
    )
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


@router.get("/{location_id}", response_model=LocationOut)
def get_location(
    project_id: str,
    location_id: UUID,
    db: Session = Depends(get_db),
):
    """获取单个地点详情。"""
    return _get_or_404(db, project_id, location_id)


@router.patch("/{location_id}", response_model=LocationOut)
def update_location(
    project_id: str,
    location_id: UUID,
    payload: LocationUpdate,
    db: Session = Depends(get_db),
):
    """局部更新地点字段（只更新请求体中包含的字段）。

    Args:
        project_id: 项目 UUID
        location_id: 地点 UUID
        payload: 地点更新请求体（所有字段可选）
        db: 数据库 Session

    Returns:
        LocationOut: 更新后的地点记录
    """
    loc = _get_or_404(db, project_id, location_id)
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(loc, field, value)
    db.commit()
    db.refresh(loc)
    return loc


@router.delete("/{location_id}", status_code=204)
def delete_location(
    project_id: str,
    location_id: UUID,
    db: Session = Depends(get_db),
):
    """删除地点。

    注意：删除后与该地点关联的 Scene.location_id 将置 NULL（数据库层 ON DELETE SET NULL 未配置，
    需调用方自行处理；或在 Scene 删除前先解除关联）。

    @param project_id: 项目 UUID
    @param location_id: 地点 UUID
    @param db: 数据库 Session
    """
    loc = _get_or_404(db, project_id, location_id)
    db.delete(loc)
    db.commit()
