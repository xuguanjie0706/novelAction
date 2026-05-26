"""章节核心 CRUD 路由。

版本历史、快照、复盘审计、人物变更日志见 chapter_version_routes.py。
辅助函数（字数统计、派生数据清理、场景绑定）见 chapter_helpers.py。
"""
import html
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Chapter, Scene
from app.schemas import ChapterCreate, ChapterOut, ChapterUpdate
from app.services.embedding_service import embed_entity_async
from app.routers.chapter_helpers import (
    count_words,
    normalize_chapter_sort_orders,
    clear_chapter_rewrite_derivatives,
    resolve_quality_debts_detaching_chapter,
    bind_scenes_to_chapter,
    build_scene_writing_outline,
)
from app.routers.chapter_version_routes import version_router

router = APIRouter(prefix="/projects/{project_id}/chapters", tags=["chapters"])
router.include_router(version_router)


@router.get("", response_model=List[ChapterOut], include_in_schema=False)
@router.get("/", response_model=List[ChapterOut])
def list_chapters(project_id: str, db: Session = Depends(get_db)):
    normalize_chapter_sort_orders(db, project_id)
    return db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.deleted_at.is_(None)
    ).order_by(Chapter.sort_order).all()


@router.post("", response_model=ChapterOut, status_code=201, include_in_schema=False)
@router.post("/", response_model=ChapterOut, status_code=201)
def create_chapter(project_id: str, payload: ChapterCreate, db: Session = Depends(get_db)):
    normalize_chapter_sort_orders(db, project_id)
    last = db.query(Chapter).filter(
        Chapter.project_id == project_id, Chapter.deleted_at.is_(None)
    ).order_by(Chapter.sort_order.desc()).first()
    next_sort_order = (last.sort_order + 1) if last else 0

    chapter = Chapter(
        project_id=project_id,
        word_count=count_words(payload.content),
        version=1,
        **payload.model_dump(exclude={"sort_order"}),
        sort_order=next_sort_order,
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)

    # 创建后立即尝试绑定场景提纲（若有匹配的 Scene）
    if chapter.outline_node_id:
        related_scenes = db.query(Scene).filter(
            (Scene.chapter_id == chapter.id) | (Scene.outline_node_id == chapter.outline_node_id)
        ).order_by(Scene.order).all()
        if related_scenes:
            outline = build_scene_writing_outline(related_scenes)
            chapter.extra = {"scene_writing_outline": outline}
            db.commit()
            db.refresh(chapter)

    return chapter


@router.get("/{chapter_id}", response_model=ChapterOut)
def get_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id, Chapter.deleted_at.is_(None)
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    return chapter


@router.patch("/{chapter_id}", response_model=ChapterOut)
def update_chapter(project_id: str, chapter_id: str, payload: ChapterUpdate, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id, Chapter.deleted_at.is_(None)
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    data = payload.model_dump(exclude_unset=True)

    # 乐观锁检查
    if "version" in data and data["version"] != chapter.version:
        raise HTTPException(409, "Chapter has been modified by another process. Please refresh and retry.")

    if "content" in data:
        data["word_count"] = count_words(data["content"])

    with db.begin_nested():
        for field, value in data.items():
            if field != "version":
                setattr(chapter, field, value)
        chapter.version = (chapter.version or 1) + 1
        db.flush()

        if "content" in data:
            # ① 绑定 Scene.chapter_id + 更新 Scene.status（内容 > 800 字时才绑定）
            _plain = re.sub(r"<[^>]+>", "", html.unescape(chapter.content or "")).strip()
            if len(_plain) > 800:
                bind_scenes_to_chapter(db, project_id, chapter)

            # ② 构建/更新写作提纲（仅在尚未生成时构建）
            if not chapter.extra or not chapter.extra.get("scene_writing_outline"):
                related_scenes = db.query(Scene).filter(
                    (Scene.chapter_id == chapter.id) | (Scene.outline_node_id == chapter.outline_node_id)
                ).order_by(Scene.order).all()
                if related_scenes:
                    outline = build_scene_writing_outline(related_scenes)
                    current_extra = dict(chapter.extra or {})
                    current_extra["scene_writing_outline"] = outline
                    chapter.extra = current_extra

    db.commit()
    normalize_chapter_sort_orders(db, project_id)
    db.refresh(chapter)

    # ③ 写章后异步生成 embedding，不阻塞响应
    if "content" in data and chapter.content:
        try:
            embed_entity_async("chapter", chapter.id, chapter.content, SessionLocal)
        except Exception:  # noqa: BLE001
            pass

    return chapter


@router.delete("/{chapter_id}", status_code=204)
def delete_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id, Chapter.deleted_at.is_(None)
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    with db.begin_nested():
        chapter.deleted_at = datetime.now(timezone.utc)
        chapter.version = (chapter.version or 1) + 1
        clear_chapter_rewrite_derivatives(db, project_id, chapter_id)
        resolve_quality_debts_detaching_chapter(db, project_id, chapter_id)
        db.flush()

    db.commit()
    normalize_chapter_sort_orders(db, project_id)
