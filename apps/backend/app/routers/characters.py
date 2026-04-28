from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Character, CharacterRelationship
from app.schemas.character import (
    CharacterCreate, CharacterUpdate, CharacterOut,
    RelationshipCreate, RelationshipOut
)

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
    return changed


@router.get("/", response_model=List[CharacterOut])
def list_characters(project_id: str, db: Session = Depends(get_db)):
    rows = db.query(Character).filter(Character.project_id == project_id).all()
    changed = False
    for row in rows:
        changed = _normalize_character_defaults(row) or changed
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
    return char


@router.patch("/{character_id}", response_model=CharacterOut)
def update_character(project_id: str, character_id: str, payload: CharacterUpdate, db: Session = Depends(get_db)):
    char = db.query(Character).filter(
        Character.id == character_id, Character.project_id == project_id
    ).first()
    if not char:
        raise HTTPException(404, "Character not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(char, field, value)
    _normalize_character_defaults(char)
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
