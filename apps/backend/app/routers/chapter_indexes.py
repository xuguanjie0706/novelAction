from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import Chapter, ChapterIndex
from app.schemas import ChapterIndexCreate, ChapterIndexUpdate, ChapterIndexOut

router = APIRouter(prefix="/projects/{project_id}/chapter-indexes", tags=["chapter-indexes"])


@router.get("/", response_model=List[ChapterIndexOut])
def list_chapter_indexes(project_id: str, db: Session = Depends(get_db)):
    return db.query(ChapterIndex).filter(
        ChapterIndex.project_id == project_id
    ).order_by(ChapterIndex.chapter_number).all()


@router.get("/chapter/{chapter_id}", response_model=ChapterIndexOut)
def get_chapter_index(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    index = db.query(ChapterIndex).filter(
        ChapterIndex.project_id == project_id,
        ChapterIndex.chapter_id == chapter_id,
    ).first()
    if not index:
        raise HTTPException(404, "Chapter index not found")
    return index


@router.post("/", response_model=ChapterIndexOut, status_code=201)
def upsert_chapter_index(project_id: str, payload: ChapterIndexCreate, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(
        Chapter.id == payload.chapter_id,
        Chapter.project_id == project_id,
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    index = db.query(ChapterIndex).filter(
        ChapterIndex.project_id == project_id,
        ChapterIndex.chapter_id == payload.chapter_id,
    ).first()
    data = payload.model_dump()
    data["project_id"] = project_id
    if index:
        for field, value in data.items():
            if field != "chapter_id":
                setattr(index, field, value)
    else:
        index = ChapterIndex(**data)
        db.add(index)
    db.commit()
    db.refresh(index)
    return index


@router.patch("/chapter/{chapter_id}", response_model=ChapterIndexOut)
def update_chapter_index(
    project_id: str,
    chapter_id: str,
    payload: ChapterIndexUpdate,
    db: Session = Depends(get_db),
):
    index = db.query(ChapterIndex).filter(
        ChapterIndex.project_id == project_id,
        ChapterIndex.chapter_id == chapter_id,
    ).first()
    if not index:
        raise HTTPException(404, "Chapter index not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(index, field, value)
    db.commit()
    db.refresh(index)
    return index
