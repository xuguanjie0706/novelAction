from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import (
    Chapter,
    ChapterDebriefCache,
    ChapterIndex,
    ChapterVersion,
    Foreshadow,
    MemoryChunk,
    QualityDebt,
)
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
    """删除章节派生数据（记忆片段、章节索引、质检债）。删整章时由 delete_chapter 调用。"""
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


def clear_chapter_rewrite_derivatives(db: Session, project_id: str, chapter_id: str) -> None:
    """
    整章重写（replace_existing）开始前调用：清掉本章旧稿派生数据，避免与新正文、新复盘叠加矛盾。

    - 记忆 / ChapterIndex / 质检债：同 delete_chapter_artifacts
    - 自动复盘草稿缓存
    - 在本章埋下的全局伏笔（旧稿线索）
    - 在本章被标记「已回收」、但埋在其他章的伏笔：解除回收，改回 open，便于新稿重新对齐
    """
    delete_chapter_artifacts(db, project_id, chapter_id)
    db.query(ChapterDebriefCache).filter(
        ChapterDebriefCache.project_id == project_id,
        ChapterDebriefCache.chapter_id == chapter_id,
    ).delete(synchronize_session=False)
    db.query(Foreshadow).filter(
        Foreshadow.project_id == project_id,
        Foreshadow.laid_chapter_id == chapter_id,
    ).delete(synchronize_session=False)
    for row in (
        db.query(Foreshadow)
        .filter(
            Foreshadow.project_id == project_id,
            Foreshadow.resolved_chapter_id == chapter_id,
        )
        .all()
    ):
        row.resolved_chapter_id = None
        row.resolved_chapter_number = None
        if row.status == "resolved":
            row.status = "open"


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


@router.get("", response_model=List[ChapterOut], include_in_schema=False)
@router.get("/", response_model=List[ChapterOut])
def list_chapters(project_id: str, db: Session = Depends(get_db)):
    normalize_chapter_sort_orders(db, project_id)
    return db.query(Chapter).filter(
        Chapter.project_id == project_id
    ).order_by(Chapter.sort_order).all()


@router.post("", response_model=ChapterOut, status_code=201, include_in_schema=False)
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
        **payload.model_dump(exclude={"sort_order"}),
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
    # 含复盘缓存、本章伏笔与 resolved 外键等，避免删 chapters 行时触发 FK 约束（仅删记忆/index/债不够）
    clear_chapter_rewrite_derivatives(db, project_id, chapter_id)
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
