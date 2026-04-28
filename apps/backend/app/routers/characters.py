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


@router.get("/", response_model=List[CharacterOut])
def list_characters(project_id: str, db: Session = Depends(get_db)):
    return db.query(Character).filter(Character.project_id == project_id).all()


@router.post("/", response_model=CharacterOut, status_code=201)
def create_character(project_id: str, payload: CharacterCreate, db: Session = Depends(get_db)):
    char = Character(project_id=project_id, **payload.model_dump())
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
