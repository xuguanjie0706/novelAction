from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models import Character, CharacterRelationship, CharacterChangeLog, OutlineNode, PowerSystem
from app.schemas.character import (
    CharacterCreate,
    CharacterUpdate,
    CharacterOut,
    CharacterGrowthTimelineOut,
    CharacterGrowthMilestoneOut,
    RelationshipCreate,
    RelationshipOut,
)
from app.routers.outline.helpers.expand_context import _outline_node_to_chapter_context
from app.routers.ai.realm_tracker import reconcile_character_realm_from_milestones
from app.routers.outline.helpers.realm_timeline import (
    _build_realm_rank_map,
    _rank_for_realm_label,
    build_character_growth_timeline,
)
from app.schemas.character_change_log import CharacterChangeLogOut

router = APIRouter(prefix="/projects/{project_id}/characters", tags=["characters"])


def _normalize_character_defaults(char: Character) -> bool:
    """兼容历史脏数据：把 NULL 字段回填为 schema 需要的默认值。"""
    changed = False
    if char.alias is None:
        char.alias = []
        changed = True
    if char.arc_stages is None:
        char.arc_stages = []
        changed = True
    if char.known_skills is None:
        char.known_skills = []
        changed = True
    if char.owned_items is None:
        char.owned_items = []
        changed = True
    if char.strengths is None:
        char.strengths = []
        changed = True
    if char.weaknesses is None:
        char.weaknesses = []
        changed = True
    if char.special_traits is None:
        char.special_traits = []
        changed = True
    if char.extra is None:
        char.extra = {}
        changed = True
    if char.current_status is None:
        char.current_status = "alive"
        changed = True
    if char.character_tier is None:
        char.character_tier = "core"
        changed = True
    return changed


@router.get("/", response_model=List[CharacterOut])
def list_characters(project_id: str, db: Session = Depends(get_db)):
    rows = db.query(Character).filter(Character.project_id == project_id).all()
    name_to_rank, _, _ = _build_realm_rank_map(
        db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()
    )
    changed = False
    for row in rows:
        changed = _normalize_character_defaults(row) or changed
        if name_to_rank and row.current_realm and row.realm_rank is None:
            resolved = _rank_for_realm_label(row.current_realm.strip(), name_to_rank)
            if resolved is not None:
                row.realm_rank = resolved
                changed = True
        if reconcile_character_realm_from_milestones(row, name_to_rank):
            changed = True
    if changed:
        db.commit()
    return rows


@router.post("/", response_model=CharacterOut, status_code=201)
def create_character(project_id: str, payload: CharacterCreate, db: Session = Depends(get_db)):
    char = Character(project_id=project_id, **payload.model_dump())
    _normalize_character_defaults(char)
    db.add(char)
    db.commit()
    db.refresh(char)
    return char


@router.get("/{character_id}", response_model=CharacterOut)
def get_character(project_id: str, character_id: str, db: Session = Depends(get_db)):
    char = db.query(Character).filter(
        Character.id == character_id, Character.project_id == project_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    if _normalize_character_defaults(char):
        db.commit()
        db.refresh(char)
    name_to_rank, _, _ = _build_realm_rank_map(
        db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()
    )
    if name_to_rank and reconcile_character_realm_from_milestones(char, name_to_rank):
        db.commit()
        db.refresh(char)
    return char


# 手动编辑时需要追踪的字段及中文标签
_TRACKED_FIELDS = {
    "current_realm":    "境界",
    "current_status":   "状态",
    "current_location": "位置",
    "character_tier":   "叙事层级",
    "faction":          "所属势力",
    "faction_rank":     "势力职位",
    "role":             "角色类型",
}


@router.patch("/{character_id}", response_model=CharacterOut)
def update_character(project_id: str, character_id: str, payload: CharacterUpdate, db: Session = Depends(get_db)):
    char = db.query(Character).filter(
        Character.id == character_id, Character.project_id == project_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")

    # 在修改前记录需要追踪的字段原值
    updates = payload.model_dump(exclude_none=True)
    changes = []
    for field, label in _TRACKED_FIELDS.items():
        if field in updates:
            before_val = getattr(char, field, None)
            after_val  = updates[field]
            if str(before_val or "") != str(after_val or ""):
                changes.append({"field": field, "label": label,
                                 "before": before_val, "after": after_val})

    for field, value in updates.items():
        setattr(char, field, value)
    _normalize_character_defaults(char)

    # 有实质变更才写审计日志
    if changes:
        log = CharacterChangeLog(
            project_id=project_id,
            character_id=char.id,
            character_name=char.name,
            source="manual",
            summary=f"手动编辑：{'、'.join(c['label'] for c in changes)}",
            changes=changes,
        )
        db.add(log)

    db.commit()
    db.refresh(char)
    return char


@router.delete("/{character_id}", status_code=204)
def delete_character(project_id: str, character_id: str, db: Session = Depends(get_db)):
    char = db.query(Character).filter(
        Character.id == character_id, Character.project_id == project_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    db.delete(char)
    db.commit()


# --- 成长轨迹（境界时间轴）---

@router.get("/{character_id}/growth-timeline", response_model=CharacterGrowthTimelineOut)
def get_character_growth_timeline(
    project_id: str,
    character_id: str,
    db: Session = Depends(get_db),
):
    """只读：从大纲人物变化/实力里程碑、复盘快照、变更记录合并该人物成长时间轴。"""
    char = db.query(Character).filter(
        Character.id == character_id,
        Character.project_id == project_id,
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")

    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
    ).all()
    chapters = [_outline_node_to_chapter_context(n) for n in nodes]
    power_systems = db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()
    change_logs = (
        db.query(CharacterChangeLog)
        .filter(
            CharacterChangeLog.project_id == project_id,
            CharacterChangeLog.character_id == character_id,
        )
        .order_by(CharacterChangeLog.created_at.asc())
        .all()
    )

    payload = build_character_growth_timeline(
        chapters,
        power_systems,
        char,
        change_logs=change_logs,
    )
    return CharacterGrowthTimelineOut(
        character_id=payload["character_id"],
        character_display_name=payload.get("character_display_name"),
        character_anchor_names=payload.get("character_anchor_names") or [],
        has_realm_whitelist=payload["has_realm_whitelist"],
        anchored=payload["anchored"],
        chapter_plans_scanned=payload["chapter_plans_scanned"],
        debrief_snapshots=payload.get("debrief_snapshots", 0),
        changelog_entries=payload.get("changelog_entries", 0),
        milestones=[CharacterGrowthMilestoneOut(**m) for m in payload["milestones"]],
        source=payload.get("source", "outline+debrief+changelog"),
    )


# --- 变更审计日志 ---

@router.get("/{character_id}/changelog", response_model=List[CharacterChangeLogOut])
def get_character_changelog(
    project_id: str,
    character_id: str,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
):
    """获取某人物的全部变更记录，按时间倒序。"""
    return (
        db.query(CharacterChangeLog)
        .filter(
            CharacterChangeLog.project_id   == project_id,
            CharacterChangeLog.character_id == character_id,
        )
        .order_by(CharacterChangeLog.created_at.desc())
        .limit(limit)
        .all()
    )


@router.delete("/{character_id}/changelog/{log_id}", status_code=204)
def delete_character_changelog_entry(
    project_id: str,
    character_id: str,
    log_id: str,
    db: Session = Depends(get_db),
):
    """删除单条变更记录。"""
    entry = db.query(CharacterChangeLog).filter(
        CharacterChangeLog.id == log_id,
        CharacterChangeLog.character_id == character_id,
        CharacterChangeLog.project_id == project_id,
    ).first()
    if not entry:
        raise HTTPException(404, "Changelog entry not found")
    db.delete(entry)
    db.commit()


@router.delete("/{character_id}/changelog", status_code=204)
def clear_character_changelog(
    project_id: str,
    character_id: str,
    db: Session = Depends(get_db),
):
    """清空某人物的全部变更记录。"""
    char = db.query(Character).filter(
        Character.id == character_id,
        Character.project_id == project_id,
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    db.query(CharacterChangeLog).filter(
        CharacterChangeLog.project_id   == project_id,
        CharacterChangeLog.character_id == character_id,
    ).delete(synchronize_session=False)
    db.commit()


# --- 关系图 ---
@router.get("/relationships/all", response_model=List[RelationshipOut])
def list_relationships(project_id: str, db: Session = Depends(get_db)):
    return db.query(CharacterRelationship).filter(
        CharacterRelationship.project_id == project_id
    ).all()


@router.post("/relationships", response_model=RelationshipOut, status_code=201)
def create_relationship(project_id: str, payload: RelationshipCreate, db: Session = Depends(get_db)):
    rel = CharacterRelationship(project_id=project_id, **payload.model_dump())
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel
