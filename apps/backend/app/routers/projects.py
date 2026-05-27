from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.dependencies import get_current_user, is_admin_user
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
    ChapterDebriefApplyRecord,
    ChapterDebriefUndo,
    ChapterCoherenceReport,
    AiChatMessage,
)
from app.models.user import User
from app.schemas import ProjectCreate, ProjectUpdate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


def _owned_or_404(db: Session, project_id: str, user: User) -> Project:
    """加载项目并校验归属当前用户，否则统一抛 404 防探测。

    管理员 token (``is_admin_user``) 跨用户放行，仅按 project_id 加载。
    """
    q = db.query(Project).filter(Project.id == project_id)
    if not is_admin_user(user):
        q = q.filter(Project.user_id == user.id)
    project = q.first()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.get("/", response_model=List[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回项目列表，按更新时间倒序。

    - 普通用户：仅返回自己名下的项目。
    - 管理员 token：返回全部用户的项目（用于管理后台跨用户审阅）。
    """
    q = db.query(Project)
    if not is_admin_user(current_user):
        q = q.filter(Project.user_id == current_user.id)
    return q.order_by(Project.updated_at.desc()).all()


@router.post("/", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建项目，user_id 强制写为当前登录用户，禁止伪造。

    管理员 token 不可创建项目（无业务用户身份），返回 403。
    """
    if is_admin_user(current_user):
        raise HTTPException(403, "管理员账号不能创建项目，请使用普通用户账号登录创作端")
    data = payload.model_dump()
    data.pop("user_id", None)  # 防伪造：忽略 payload 内潜在的 user_id 字段
    project = Project(**data, user_id=current_user.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _owned_or_404(db, project_id, current_user)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _owned_or_404(db, project_id, current_user)
    update_data = payload.model_dump(exclude_none=True)
    extra_patch = update_data.pop("extra", None)

    for field, value in update_data.items():
        if field == "user_id":
            continue  # 不允许通过 PATCH 改变项目归属
        setattr(project, field, value)

    if extra_patch is not None:
        extra = dict(project.extra) if isinstance(project.extra, dict) else {}
        extra.update(extra_patch)
        project.extra = extra

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _owned_or_404(db, project_id, current_user)
    db.delete(project)
    db.commit()


@router.post("/{project_id}/reset-writing")
def reset_writing_progress(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    重置写作进度：保留大纲/世界观/境界体系/势力，清除：
    - 所有章节正文及版本
    - 记忆库 / 伏笔 / 章节索引 / 复盘缓存 / undo / 质检债（待处理→已修复并解除章节关联，不物理删）/ 连贯性报告 / AI对话
    - 技能 / 道具（Bootstrap 可重新生成）
    - 人物写作状态（境界/位置/已学技能/持有道具/成长阶段，基础档案保留）
    - 人物变更日志
    - 故事线推进记录 key_beats（定义保留）
    """
    project = _owned_or_404(db, project_id, current_user)

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
    stats["debrief_apply_records"] = db.query(ChapterDebriefApplyRecord).filter(
        ChapterDebriefApplyRecord.project_id == pid
    ).delete(synchronize_session=False)
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


class WritingConfigUpdate(BaseModel):
    """PATCH /projects/{id}/writing-config 的请求体。所有字段可选，只更新传入的字段。"""
    auto_quality_gate: Optional[bool] = None
    min_overall_score: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    min_subscribe_intent: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    max_rewrite_attempts: Optional[int] = Field(default=None, ge=1, le=5)
    pre_write_warning_enabled: Optional[bool] = None


@router.patch("/{project_id}/writing-config")
def update_writing_config(
    project_id: str,
    payload: WritingConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新项目级写作配置（质量门控参数）。

    配置存储于 Project.extra.writing_config，只更新请求体中明确传入的字段，
    其余保持不变。返回更新后的完整 writing_config。

    Args:
        project_id: 项目 UUID
        payload: 部分更新字段（auto_quality_gate / min_overall_score /
                 min_subscribe_intent / max_rewrite_attempts）
    Returns:
        {"writing_config": {...}} — 更新后的完整配置
    """
    project = _owned_or_404(db, project_id, current_user)

    extra = dict(project.extra) if isinstance(project.extra, dict) else {}
    cfg = dict(extra.get("writing_config") or {})

    update_data = payload.model_dump(exclude_none=True)
    cfg.update(update_data)

    extra["writing_config"] = cfg
    project.extra = extra
    db.commit()
    db.refresh(project)

    return {"writing_config": (project.extra or {}).get("writing_config", {})}


@router.get("/{project_id}/writing-config")
def get_writing_config(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    读取项目级写作配置，缺省字段返回系统默认值。

    @returns {"writing_config": {...}}
    """
    project = _owned_or_404(db, project_id, current_user)

    defaults = {
        "auto_quality_gate": True,
        "min_overall_score": 6.0,
        "min_subscribe_intent": 6.0,
        "max_rewrite_attempts": 3,
        "pre_write_warning_enabled": False,
    }
    stored = (project.extra or {}).get("writing_config") or {}
    merged = {**defaults, **stored}
    return {"writing_config": merged}


@router.get("/{project_id}/insights")
def get_project_insights(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    返回 Bootstrap 生成后写入 Project.extra 的编辑视角洞察数据：
    - consistency_issues：全局一致性扫描结果（Step 12）
    - opening_contract：开局前10章追读承诺清单（Step 12）
    调用方：Bootstrap 完成页、项目概览、写前预警。
    """
    from app.services.bootstrap.opening_contract_io import resolve_opening_contract

    project = _owned_or_404(db, project_id, current_user)
    extra = project.extra if isinstance(project.extra, dict) else {}
    return {
        "project_id": str(project.id),
        "consistency_issues": extra.get("consistency_issues") or [],
        "opening_contract": resolve_opening_contract(db, project),
        "positioning": extra.get("positioning") or {},
    }
