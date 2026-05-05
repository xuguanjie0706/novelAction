from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import (
    Project,
    Chapter, ChapterVersion,
    MemoryChunk,
    Foreshadow,
    ChapterIndex,
    Character,
    CharacterRelationship,
    CharacterChangeLog,
    Skill,
    Item,
    StoryLine,
    QualityDebt,
    ChapterDebriefCache,
    ChapterDebriefUndo,
    ChapterCoherenceReport,
    AiChatMessage,
)
from app.schemas import ProjectCreate, ProjectUpdate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/", response_model=List[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.updated_at.desc()).all()


@router.post("/", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    db.delete(project)
    db.commit()


@router.post("/{project_id}/reset-writing")
def reset_writing_progress(project_id: str, db: Session = Depends(get_db)):
    """
    重置写作进度：保留大纲/世界观/境界体系/势力，清除：
    - 所有章节正文及版本
    - 记忆库 / 伏笔 / 章节索引 / 复盘缓存 / undo / 质检债（待处理→已修复并解除章节关联，不物理删）/ 连贯性报告 / AI对话
    - 技能 / 道具（Bootstrap 可重新生成）
    - 人物写作状态（境界/位置/已学技能/持有道具/成长阶段，基础档案保留）
    - 人物变更日志
    - 故事线推进记录 key_beats（定义保留）
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    pid = project_id
    stats: dict = {}

    # ── 0. 质检债：不物理删除，待处理标为已修复并解除章节外键（随后会删章节）────────
    stats["quality_debts_pending_resolved"] = db.query(QualityDebt).filter(
        QualityDebt.project_id == pid,
        QualityDebt.status == "pending",
    ).update({"status": "resolved"}, synchronize_session=False)
    stats["quality_debts_detached"] = db.query(QualityDebt).filter(
        QualityDebt.project_id == pid,
    ).update({"chapter_id": None}, synchronize_session=False)

    # ── 1. 章节 & 版本 ────────────────────────────────────
    stats["chapters"] = db.query(Chapter).filter(Chapter.project_id == pid).delete(synchronize_session=False)
    # ChapterVersion 级联删除（依赖 Chapter FK），但为防止无级联配置，显式清
    stats["chapter_versions"] = db.query(ChapterVersion).filter(ChapterVersion.project_id == pid).delete(synchronize_session=False)

    # ── 2. 章节衍生数据 ───────────────────────────────────
    stats["memories"] = db.query(MemoryChunk).filter(MemoryChunk.project_id == pid).delete(synchronize_session=False)
    stats["foreshadows"] = db.query(Foreshadow).filter(Foreshadow.project_id == pid).delete(synchronize_session=False)
    stats["chapter_indexes"] = db.query(ChapterIndex).filter(ChapterIndex.project_id == pid).delete(synchronize_session=False)
    stats["debrief_caches"] = db.query(ChapterDebriefCache).filter(ChapterDebriefCache.project_id == pid).delete(synchronize_session=False)
    stats["debrief_undos"] = db.query(ChapterDebriefUndo).filter(ChapterDebriefUndo.project_id == pid).delete(synchronize_session=False)
    stats["coherence_reports"] = db.query(ChapterCoherenceReport).filter(ChapterCoherenceReport.project_id == pid).delete(synchronize_session=False)
    stats["ai_messages"] = db.query(AiChatMessage).filter(AiChatMessage.project_id == pid).delete(synchronize_session=False)
    stats["char_change_logs"] = db.query(CharacterChangeLog).filter(CharacterChangeLog.project_id == pid).delete(synchronize_session=False)

    # ── 3. 技能 & 道具（可由 Bootstrap 重新生成）──────────
    stats["skills"] = db.query(Skill).filter(Skill.project_id == pid).delete(synchronize_session=False)
    stats["items"] = db.query(Item).filter(Item.project_id == pid).delete(synchronize_session=False)

    # ── 4. 人物：仅清写作状态，保留基础档案 ──────────────
    chars = db.query(Character).filter(Character.project_id == pid).all()
    for c in chars:
        c.current_realm = None
        c.realm_rank = None
        c.current_location = None
        c.current_status = "alive"
        c.known_skills = []
        c.owned_items = []
        c.arc_stages = []
        # 清除 extra 中的复盘里程碑，保留其他 extra 字段
        if isinstance(c.extra, dict) and "debrief_realm_milestones" in c.extra:
            c.extra = {k: v for k, v in c.extra.items() if k != "debrief_realm_milestones"}
    stats["chars_reset"] = len(chars)

    # ── 5. 故事线：清 key_beats，保留定义 ────────────────
    storylines = db.query(StoryLine).filter(StoryLine.project_id == pid).all()
    for sl in storylines:
        sl.key_beats = []
        sl.status = "planned"
    stats["storylines_reset"] = len(storylines)

    db.commit()

    total_deleted = sum(v for k, v in stats.items() if k not in ("chars_reset", "storylines_reset"))
    return {
        "message": (
            f"写作进度已重置：删除 {total_deleted} 条数据，"
            f"重置 {stats['chars_reset']} 个人物状态、"
            f"{stats['storylines_reset']} 条故事线进度"
        ),
        "stats": stats,
    }
