from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Chapter, ChapterIndex, ChapterVersion, MemoryChunk, QualityDebt
from app.schemas import ChapterCreate, ChapterUpdate, ChapterOut, ChapterVersionOut

router = APIRouter(prefix="/projects/{project_id}/chapters", tags=["chapters"])


def count_words(text: str) -> int:
    """简易中文字数统计（去 HTML 标签）"""
    import re
    clean = re.sub(r"<[^>]+>", "", text or "")
    # 中文字符 + 英文单词
    chinese = len(re.findall(r"[一-鿿]", clean))
    english = len(re.findall(r"[a-zA-Z]+", clean))
    return chinese + english


def delete_chapter_artifacts(db: Session, project_id: str, chapter_id: str) -> None:
    """删除章节派生数据，避免重写/重建章节时读到旧记忆和旧索引。"""
    db.query(MemoryChunk).filter(
        MemoryChunk.project_id == project_id,
        MemoryChunk.chapter_id == chapter_id,
    ).delete(synchronize_session=False)
    db.query(ChapterIndex).filter(
        ChapterIndex.project_id == project_id,
        ChapterIndex.chapter_id == chapter_id,
    ).delete(synchronize_session=False)
    db.query(QualityDebt).filter(
        QualityDebt.project_id == project_id,
        QualityDebt.chapter_id == chapter_id,
    ).delete(synchronize_session=False)


def normalize_chapter_sort_orders(db: Session, project_id: str) -> None:
    """
    统一章节排序为连续整数，避免历史数据出现重复/空洞 sort_order 导致前端显示错乱。
    """
    chapters = db.query(Chapter).filter(
        Chapter.project_id == project_id
    ).order_by(Chapter.sort_order, Chapter.created_at, Chapter.id).all()
    changed = False
    for index, chapter in enumerate(chapters):
        if chapter.sort_order != index:
            chapter.sort_order = index
            changed = True
    if changed:
        db.commit()


@router.get("/", response_model=List[ChapterOut])
def list_chapters(project_id: str, db: Session = Depends(get_db)):
    normalize_chapter_sort_orders(db, project_id)
    return db.query(Chapter).filter(
        Chapter.project_id == project_id
    ).order_by(Chapter.sort_order).all()


@router.post("/", response_model=ChapterOut, status_code=201)
def create_chapter(project_id: str, payload: ChapterCreate, db: Session = Depends(get_db)):
    normalize_chapter_sort_orders(db, project_id)
    last = db.query(Chapter).filter(
        Chapter.project_id == project_id
    ).order_by(Chapter.sort_order.desc()).first()
    next_sort_order = (last.sort_order + 1) if last else 0

    chapter = Chapter(
        project_id=project_id,
        word_count=count_words(payload.content),
        **payload.model_dump(),
        sort_order=next_sort_order,
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


@router.get("/{chapter_id}", response_model=ChapterOut)
def get_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    return chapter


@router.patch("/{chapter_id}", response_model=ChapterOut)
def update_chapter(project_id: str, chapter_id: str, payload: ChapterUpdate, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    data = payload.model_dump(exclude_none=True)
    if "content" in data:
        data["word_count"] = count_words(data["content"])
    for field, value in data.items():
        setattr(chapter, field, value)
    db.commit()
    normalize_chapter_sort_orders(db, project_id)
    db.refresh(chapter)
    return chapter


@router.delete("/{chapter_id}", status_code=204)
def delete_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    delete_chapter_artifacts(db, project_id, chapter_id)
    db.delete(chapter)
    db.commit()
    normalize_chapter_sort_orders(db, project_id)


# --- 版本历史 ---
@router.post("/{chapter_id}/snapshot", response_model=ChapterVersionOut, status_code=201)
def create_snapshot(
    project_id: str, chapter_id: str, note: str = "",
    is_auto: bool = False, db: Session = Depends(get_db)
):
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    version = ChapterVersion(
        chapter_id=chapter_id,
        content=chapter.content,
        word_count=chapter.word_count,
        note=note,
        is_auto=is_auto,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.get("/{chapter_id}/versions", response_model=List[ChapterVersionOut])
def list_versions(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    return db.query(ChapterVersion).filter(
        ChapterVersion.chapter_id == chapter_id
    ).order_by(ChapterVersion.created_at.desc()).all()
