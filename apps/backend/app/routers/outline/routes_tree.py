"""大纲树 CRUD 与主角境界时间轴。"""

from __future__ import annotations

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, Character, CharacterChangeLog, OutlineNode, PowerSystem, Project
from app.schemas import OutlineNodeCreate, OutlineNodeUpdate, OutlineNodeOut

from app.routers.outline.helpers_core import (
    _collect_protagonist_anchor_names,
    _outline_node_to_chapter_context,
    build_character_growth_timeline,
    build_tree,
)
from app.routers.outline.schemas import (
    ChapterPlansClearResult,
    ProtagonistRealmMilestoneOut,
    ProtagonistRealmTimelineOut,
)

router = APIRouter()

@router.get("/", response_model=List[OutlineNodeOut])
def get_outline_tree(project_id: str, db: Session = Depends(get_db)):
    from app.services.bootstrap.protagonist_progression import backfill_volume_protagonist_realms

    # 存量卷骨架可能仅有 BOSS 境界、缺主角起止（Step 9 升级前生成）
    backfill_volume_protagonist_realms(db, project_id)
    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id
    ).order_by(OutlineNode.sort_order, OutlineNode.created_at).all()
    return build_tree(nodes)


@router.get("/protagonist-realm-timeline", response_model=ProtagonistRealmTimelineOut)
def get_protagonist_realm_timeline(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
    ).all()
    chapters = [_outline_node_to_chapter_context(n) for n in nodes]

    characters = db.query(Character).filter(Character.project_id == project_id).all()
    power_systems = db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()
    protagonist_names = _collect_protagonist_anchor_names(characters)
    protagonist = next((c for c in characters if getattr(c, "role", None) == "protagonist"), None)
    if not protagonist:
        return ProtagonistRealmTimelineOut(
            protagonist_display_name=None,
            protagonist_anchor_names=protagonist_names,
            has_realm_whitelist=False,
            anchored=False,
            chapter_plans_scanned=0,
            debrief_snapshots=0,
            milestones=[],
        )

    change_logs = (
        db.query(CharacterChangeLog)
        .filter(
            CharacterChangeLog.project_id == project_id,
            CharacterChangeLog.character_id == protagonist.id,
        )
        .order_by(CharacterChangeLog.created_at.asc())
        .all()
    )
    payload = build_character_growth_timeline(
        chapters,
        power_systems,
        protagonist,
        change_logs=change_logs,
    )
    return ProtagonistRealmTimelineOut(
        protagonist_display_name=getattr(protagonist, "name", None),
        protagonist_anchor_names=protagonist_names,
        has_realm_whitelist=payload["has_realm_whitelist"],
        anchored=payload["anchored"],
        chapter_plans_scanned=payload["chapter_plans_scanned"],
        debrief_snapshots=payload.get("debrief_snapshots", 0),
        milestones=[ProtagonistRealmMilestoneOut(**m) for m in payload["milestones"]],
    )


@router.post("/", response_model=OutlineNodeOut, status_code=201)
def create_node(project_id: str, payload: OutlineNodeCreate, db: Session = Depends(get_db)):
    if payload.node_type == "chapter_plan" and payload.parent_id:
        parent = db.query(OutlineNode).filter(
            OutlineNode.id == payload.parent_id,
            OutlineNode.project_id == project_id,
        ).first()
        if parent and parent.node_type in ("volume", "arc"):
            raise HTTPException(
                422,
                "章节计划须由 AI「展开章纲」生成，不支持手动创建。",
            )
    node = OutlineNode(project_id=project_id, **payload.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    return OutlineNodeOut.model_validate(node)


@router.patch("/{node_id}", response_model=OutlineNodeOut)
def update_node(project_id: str, node_id: str, payload: OutlineNodeUpdate, db: Session = Depends(get_db)):
    node = db.query(OutlineNode).filter(
        OutlineNode.id == node_id, OutlineNode.project_id == project_id
    ).first()
    if not node:
        raise HTTPException(404, "Outline node not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(node, field, value)
    db.commit()
    db.refresh(node)
    return OutlineNodeOut.model_validate(node)


@router.delete("/chapter-plans", response_model=ChapterPlansClearResult)
def delete_all_chapter_plans(project_id: str, db: Session = Depends(get_db)):
    """
    删除项目中全部章节计划（chapter_plan）节点，保留卷 / 篇。
    已绑定大纲的写作章节仅解除 outline_node_id，不删除正文。
    """
    plan_ids = [
        row[0]
        for row in db.query(OutlineNode.id).filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "chapter_plan",
        ).all()
    ]
    if not plan_ids:
        return ChapterPlansClearResult(deleted=0)

    db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.outline_node_id.in_(plan_ids),
    ).update({"outline_node_id": None}, synchronize_session=False)

    deleted = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
    ).delete(synchronize_session=False)

    db.commit()
    return ChapterPlansClearResult(deleted=deleted)


@router.delete("/{node_id}", status_code=204)
def delete_node(project_id: str, node_id: str, db: Session = Depends(get_db)):
    node = db.query(OutlineNode).filter(
        OutlineNode.id == node_id, OutlineNode.project_id == project_id
    ).first()
    if not node:
        raise HTTPException(404, "Outline node not found")
    db.delete(node)
    db.commit()
