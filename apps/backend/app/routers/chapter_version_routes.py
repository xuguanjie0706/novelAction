"""章节版本快照与审计路由。

挂载到主 chapters router，提供以下端点：
- GET  /version-timeline                       本项目跨章版本时间线
- POST /{chapter_id}/snapshot                  手动/自动快照
- GET  /{chapter_id}/versions                  快照列表
- GET  /{chapter_id}/versions/{version_id}     快照详情
- GET  /{chapter_id}/debrief-apply-records     复盘提交审计
- GET  /{chapter_id}/changelog                 人物变更日志
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Chapter,
    CharacterChangeLog,
    ChapterDebriefApplyRecord,
    ChapterVersion,
    Project,
)
from app.schemas import (
    ChapterVersionDetailOut,
    ChapterVersionOut,
    ChapterVersionTimelineItemOut,
)
from app.schemas.character_change_log import CharacterChangeLogOut
from app.routers.chapter_helpers import count_words

version_router = APIRouter(tags=["chapter-versions"])


@version_router.get("/version-timeline", response_model=List[ChapterVersionTimelineItemOut])
def list_chapter_version_timeline(
    project_id: str,
    limit: int = Query(80, ge=1, le=200),
    auto_only: bool = Query(False, description="仅自动快照（如连贯性改正前）"),
    db: Session = Depends(get_db),
):
    """本项目下所有章节的版本快照时间线（新→旧）。
    连贯性「写入数据库」前会先落一条修订前快照，便于对照 LLM 改正。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    q = (
        db.query(ChapterVersion, Chapter)
        .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
        .filter(Chapter.project_id == project_id)
    )
    if auto_only:
        q = q.filter(ChapterVersion.is_auto.is_(True))

    rows = q.order_by(ChapterVersion.created_at.desc()).limit(limit).all()
    return [
        ChapterVersionTimelineItemOut(
            id=v.id,
            chapter_id=v.chapter_id,
            chapter_title=ch.title,
            chapter_sort_order=ch.sort_order,
            word_count=v.word_count,
            note=v.note,
            is_auto=bool(v.is_auto),
            created_at=v.created_at,
        )
        for v, ch in rows
    ]


@version_router.post("/{chapter_id}/snapshot", response_model=ChapterVersionOut, status_code=201)
def create_snapshot(
    project_id: str, chapter_id: str, note: str = "",
    is_auto: bool = False, db: Session = Depends(get_db)
):
    """为指定章节创建内容快照。is_auto=True 标记为系统自动快照（如连贯性改写前备份）。"""
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    snap_wc = count_words(chapter.content or "")
    version = ChapterVersion(
        chapter_id=chapter_id,
        content=chapter.content,
        word_count=snap_wc,
        note=note,
        is_auto=is_auto,
    )
    db.add(version)
    if chapter.word_count != snap_wc:
        chapter.word_count = snap_wc
    db.commit()
    db.refresh(version)
    return version


@version_router.get("/{chapter_id}/versions", response_model=List[ChapterVersionOut])
def list_versions(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    """列出章节所有快照（新→旧）。"""
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    return db.query(ChapterVersion).filter(
        ChapterVersion.chapter_id == chapter_id
    ).order_by(ChapterVersion.created_at.desc()).all()


@version_router.get("/{chapter_id}/versions/{version_id}", response_model=ChapterVersionDetailOut)
def get_version(
    project_id: str,
    chapter_id: str,
    version_id: str,
    db: Session = Depends(get_db),
):
    """获取单条快照详情（含完整正文）。"""
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    version = db.query(ChapterVersion).filter(
        ChapterVersion.id == version_id,
        ChapterVersion.chapter_id == chapter_id,
    ).first()
    if not version:
        raise HTTPException(404, "Version not found")
    return version


@version_router.get("/{chapter_id}/debrief-apply-records")
def list_chapter_debrief_apply_records(
    project_id: str,
    chapter_id: str,
    limit: int = Query(40, ge=1, le=100),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """本章历次复盘提交审计：来源（队列自动 / Tab 手动）、当时正文哈希、完整请求体快照、结果摘要。"""
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    rows = (
        db.query(ChapterDebriefApplyRecord)
        .filter(
            ChapterDebriefApplyRecord.project_id == project_id,
            ChapterDebriefApplyRecord.chapter_id == chapter_id,
        )
        .order_by(ChapterDebriefApplyRecord.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "apply_source": r.apply_source,
            "content_hash": r.content_hash,
            "payload": r.payload or {},
            "result_message": r.result_message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@version_router.get("/{chapter_id}/changelog", response_model=List[CharacterChangeLogOut])
def get_chapter_character_changelog(
    project_id: str,
    chapter_id: str,
    db: Session = Depends(get_db),
):
    """获取某章节涉及的所有人物变更，用于复盘总览。"""
    return (
        db.query(CharacterChangeLog)
        .filter(
            CharacterChangeLog.project_id == project_id,
            CharacterChangeLog.chapter_id == chapter_id,
        )
        .order_by(CharacterChangeLog.created_at.asc())
        .all()
    )
