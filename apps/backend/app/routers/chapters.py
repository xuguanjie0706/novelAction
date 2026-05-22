from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Any, Dict, List
from datetime import datetime, timezone
from app.database import get_db, SessionLocal
from app.models import (
    CharacterChangeLog,
    Chapter,
    ChapterDebriefApplyRecord,
    ChapterDebriefCache,
    ChapterDebriefUndo,
    ChapterIndex,
    ChapterVersion,
    Character,
    Foreshadow,
    MemoryChunk,
    Project,
    QualityDebt,
    ReaderPromise,
    Scene,
    StoryLine,
)
from app.schemas import (
    ChapterCreate,
    ChapterUpdate,
    ChapterOut,
    ChapterVersionOut,
    ChapterVersionDetailOut,
    ChapterVersionTimelineItemOut,
)
from app.schemas.character_change_log import CharacterChangeLogOut
from app.services.embedding_service import embed_entity_async

router = APIRouter(prefix="/projects/{project_id}/chapters", tags=["chapters"])


def resolve_quality_debts_detaching_chapter(db: Session, project_id: str, chapter_id: str) -> None:
    """不硬删质量债务：待处理标为已修复，并解除 chapter_id 以便删除章节行。"""
    db.query(QualityDebt).filter(
        QualityDebt.project_id == project_id,
        QualityDebt.chapter_id == chapter_id,
        QualityDebt.status == "pending",
    ).update({"status": "resolved"}, synchronize_session=False)
    db.query(QualityDebt).filter(
        QualityDebt.project_id == project_id,
        QualityDebt.chapter_id == chapter_id,
    ).update({"chapter_id": None}, synchronize_session=False)


def count_words(text: str) -> int:
    """改进的中文字数统计：先剥离 HTML 标签，再统计 CJK 字符 + 英文/数字单词。"""
    import re
    import html
    if not text:
        return 0
    # 解码 HTML 实体
    decoded = html.unescape(text)
    # 剥离 HTML 标签
    clean = re.sub(r"<[^>]+>", "", decoded)
    # 统计：CJK 统一表意文字（含扩展）+ 英文/数字单词
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3400-\u4dbf\U00020000-\U0002a6df]", clean))
    words = len(re.findall(r"[a-zA-Z0-9]+", clean))
    return cjk + words


def delete_chapter_artifacts(
    db: Session,
    project_id: str,
    chapter_id: str,
    *,
    with_quality_debts: bool = True,
) -> None:
    """删除章节派生数据（记忆片段、章节索引、可选质检债）。

    `with_quality_debts=False` 用于「改稿/重写」清缓存：不碰质量债务行。
    `with_quality_debts=True`：将本章关联债务标为已修复并解除 chapter_id（不删行）。
    """
    db.query(MemoryChunk).filter(
        MemoryChunk.project_id == project_id,
        MemoryChunk.chapter_id == chapter_id,
    ).delete(synchronize_session=False)
    db.query(ChapterIndex).filter(
        ChapterIndex.project_id == project_id,
        ChapterIndex.chapter_id == chapter_id,
    ).delete(synchronize_session=False)
    if with_quality_debts:
        resolve_quality_debts_detaching_chapter(db, project_id, chapter_id)


def clear_chapter_rewrite_derivatives(db: Session, project_id: str, chapter_id: str) -> None:
    """
    整章重写（replace_existing）或删章前调用：清掉本章旧稿派生数据，避免与新正文、新复盘叠加矛盾。

    处理顺序：
    1. 从 undo 快照回滚覆盖型字段（character realm/location/status/realm_rank、storyline status）
    2. 按 chapter_id 精确清除追加型数据（storyline beats、character known_skills/owned_items）
    3. 清除 realm_milestones 快照中本章记录
    4. 清除记忆 / ChapterIndex / 复盘缓存 / 伏笔 / 读者承诺 / 复盘变更日志（不删质量债务行）
    5. 删除 undo 快照行
    """
    # ── 1. 回滚覆盖型字段 ─────────────────────────��────
    undo = db.query(ChapterDebriefUndo).filter(
        ChapterDebriefUndo.chapter_id == chapter_id
    ).first()
    if undo:
        for snap in (undo.char_states or []):
            cid = snap.get("character_id")
            if not cid:
                continue
            char = db.query(Character).filter(
                Character.id == cid,
                Character.project_id == project_id,
            ).first()
            if not char:
                continue
            if snap.get("current_realm") is not None:
                char.current_realm = snap["current_realm"]
            if snap.get("current_location") is not None:
                char.current_location = snap["current_location"]
            if snap.get("current_status") is not None:
                char.current_status = snap["current_status"]
            if snap.get("realm_rank") is not None:
                char.realm_rank = snap["realm_rank"]

        for snap in (undo.storyline_statuses or []):
            sid = snap.get("storyline_id")
            if not sid:
                continue
            sl = db.query(StoryLine).filter(
                StoryLine.id == sid,
                StoryLine.project_id == project_id,
            ).first()
            if sl and snap.get("status") is not None:
                sl.status = snap["status"]

    # ── 2. 清除追加型数据（beats / skills / items）────────
    for sl in db.query(StoryLine).filter(StoryLine.project_id == project_id).all():
        if sl.key_beats:
            cleaned = [
                b for b in sl.key_beats
                if not (isinstance(b, dict) and b.get("chapter_id") == chapter_id)
            ]
            if len(cleaned) != len(sl.key_beats):
                sl.key_beats = cleaned

    for char in db.query(Character).filter(Character.project_id == project_id).all():
        changed = False
        if char.known_skills:
            cleaned = [
                s for s in char.known_skills
                if not (isinstance(s, dict) and s.get("from_chapter_id") == chapter_id)
            ]
            if len(cleaned) != len(char.known_skills):
                char.known_skills = cleaned
                changed = True
        if char.owned_items:
            cleaned = [
                i for i in char.owned_items
                if not (isinstance(i, dict) and i.get("from_chapter_id") == chapter_id)
            ]
            if len(cleaned) != len(char.owned_items):
                char.owned_items = cleaned
                changed = True
        # ── 3. 清除 realm_milestones 中本章记录 ────────
        if isinstance(char.extra, dict) and char.extra.get("debrief_realm_milestones"):
            milestones = char.extra["debrief_realm_milestones"]
            cleaned_ms = [
                m for m in milestones
                if not (isinstance(m, dict) and m.get("chapter_id") == chapter_id)
            ]
            if len(cleaned_ms) != len(milestones):
                char.extra = {**char.extra, "debrief_realm_milestones": cleaned_ms}
                changed = True

    # ── 4. 清除记忆 / ChapterIndex / 复盘缓存 / 伏笔（不碰质量债务，见 delete_chapter_artifacts）──
    delete_chapter_artifacts(db, project_id, chapter_id, with_quality_debts=False)
    db.query(ChapterDebriefCache).filter(
        ChapterDebriefCache.project_id == project_id,
        ChapterDebriefCache.chapter_id == chapter_id,
    ).delete(synchronize_session=False)
    db.query(ChapterDebriefApplyRecord).filter(
        ChapterDebriefApplyRecord.project_id == project_id,
        ChapterDebriefApplyRecord.chapter_id == chapter_id,
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

    # ── 4b. 读者承诺：本章埋下的删除；本章兑现的回退为 open ─────────────
    db.query(ReaderPromise).filter(
        ReaderPromise.project_id == project_id,
        ReaderPromise.source_chapter_id == chapter_id,
    ).delete(synchronize_session=False)
    for rp in (
        db.query(ReaderPromise)
        .filter(
            ReaderPromise.project_id == project_id,
            ReaderPromise.fulfilled_chapter_id == chapter_id,
        )
        .all()
    ):
        rp.fulfilled_chapter_id = None
        rp.fulfilled_chapter_number = None
        if rp.status == "fulfilled":
            rp.status = "open"

    # ── 4c. 本章复盘审计日志（避免重写后人物变更记录重复）────────────
    db.query(CharacterChangeLog).filter(
        CharacterChangeLog.project_id == project_id,
        CharacterChangeLog.chapter_id == chapter_id,
        CharacterChangeLog.source == "debrief",
    ).delete(synchronize_session=False)

    # ── 5. 删除 undo 快照 ─────────────────────────────
    if undo:
        db.delete(undo)


def normalize_chapter_sort_orders(db: Session, project_id: str) -> None:
    """
    统一章节排序为连续整数，避免历史数据出现重复/空洞 sort_order 导致前端显示错乱。
    软删除章节不参与排序重整。
    """
    chapters = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.deleted_at.is_(None)
    ).order_by(Chapter.sort_order, Chapter.created_at, Chapter.id).all()
    changed = False
    for index, chapter in enumerate(chapters):
        if chapter.sort_order != index:
            chapter.sort_order = index
            changed = True
    if changed:
        db.commit()


def bind_scenes_to_chapter(db: Session, project_id: str, chapter: "Chapter") -> int:
    """
    将大纲节点关联的 Scene 记录绑定到已写完的章节，并更新 Scene 状态。

    绑定条件：
    - `chapter.outline_node_id` 存在
    - Scene.chapter_id 为 null（避免重复绑定）

    副作用：
    - Scene.chapter_id = chapter.id
    - Scene.status: "planned" → "written"

    @returns 实际绑定的 Scene 数量；outline_node_id 缺失时返回 0。
    """
    if not chapter.outline_node_id:
        return 0

    unbound_scenes = (
        db.query(Scene)
        .filter(
            Scene.project_id == project_id,
            Scene.outline_node_id == chapter.outline_node_id,
            Scene.chapter_id.is_(None),
        )
        .all()
    )
    for sc in unbound_scenes:
        sc.chapter_id = chapter.id
        if sc.status == "planned":
            sc.status = "written"

    return len(unbound_scenes)


def build_scene_writing_outline(scenes: list["Scene"]) -> dict:
    """从 Scene 列表构建结构化写作提纲，持久化到 chapter.extra.scene_writing_outline。
    前端/AI 可直接使用此提纲生成正文或展示分场指导。
    """
    items = []
    for s in scenes:
        pov_name = None
        if s.pov_character:
            pov_name = s.pov_character.name
        items.append({
            "order": s.order,
            "title": s.title or f"第{s.order}场",
            "time": s.time,
            "location": s.location_name,
            "pov_character_id": str(s.pov_character_id) if s.pov_character_id else None,
            "pov_name": pov_name,
            "goal": s.goal,
            "conflict": s.conflict,
            "turn": s.turn,
            "hook": s.hook,
            "hook_strength": s.hook_strength,
            "word_budget": s.word_budget,
            "pacing": s.pacing,
        })
    return {
        "scenes": items,
        "total_scenes": len(items),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("", response_model=List[ChapterOut], include_in_schema=False)
@router.get("/", response_model=List[ChapterOut])
def list_chapters(project_id: str, db: Session = Depends(get_db)):
    normalize_chapter_sort_orders(db, project_id)
    return db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.deleted_at.is_(None)  # 软删除过滤
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


@router.get("/version-timeline", response_model=List[ChapterVersionTimelineItemOut])
def list_chapter_version_timeline(
    project_id: str,
    limit: int = Query(80, ge=1, le=200),
    auto_only: bool = Query(False, description="仅自动快照（如连贯性改正前）"),
    db: Session = Depends(get_db),
):
    """
    本项目下所有章节的版本快照时间线（新→旧）。
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


@router.get("/{chapter_id}/debrief-apply-records")
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

    # 使用嵌套事务包裹多表操作（清理派生数据 + 更新章节）
    with db.begin_nested():
        for field, value in data.items():
            if field != "version":  # version 由系统自增
                setattr(chapter, field, value)
        chapter.version = (chapter.version or 1) + 1
        db.flush()  # 确保 version 更新在事务内

        # 场景-章节联动：保存内容时同步执行两个闭环操作
        if "content" in data:
            # ① 绑定 Scene.chapter_id + 更新 Scene.status（planned → written）
            # 仅当正文已有实质性内容（去 HTML 纯文本 > 800 字符）时才绑定，
            # 避免自动保存草稿阶段就把 Scene 标记为 written。
            import re as _re, html as _html
            _plain = _re.sub(r"<[^>]+>", "", _html.unescape(chapter.content or "")).strip()
            if len(_plain) > 800:
                bind_scenes_to_chapter(db, project_id, chapter)

            # ② 构建/更新写作提纲（前端展示用，仅在尚未生成时构建）
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

    # ③ 写章后异步生成 embedding（章节语义检索），不阻塞响应
    # 注意：传入 SessionLocal（不是 get_db），_do_embed_entity 内部直接实例化 session
    # 承诺兑现检测已迁移至复盘 apply_debrief（从结构化 fulfilled_promise_texts 读取），
    # 不再在 update_chapter 阶段从正文字符串解析。
    if "content" in data and chapter.content:
        try:
            embed_entity_async("chapter", chapter.id, chapter.content, SessionLocal)
        except Exception:  # noqa: BLE001
            pass  # 静默失败，不影响主流程

    return chapter


@router.delete("/{chapter_id}", status_code=204)
def delete_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id, Chapter.deleted_at.is_(None)
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    # 软删除 + 清理派生数据（使用嵌套事务保证原子性）
    with db.begin_nested():
        from datetime import datetime, timezone
        chapter.deleted_at = datetime.now(timezone.utc)
        chapter.version = (chapter.version or 1) + 1
        # 清理派生数据（记忆、索引、质量债务解绑等）
        clear_chapter_rewrite_derivatives(db, project_id, chapter_id)
        resolve_quality_debts_detaching_chapter(db, project_id, chapter_id)
        db.flush()

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
    # 以正文实际内容为准；避免 chapters.word_count 未同步时快照列表显示 0 字
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


@router.get("/{chapter_id}/versions", response_model=List[ChapterVersionOut])
def list_versions(project_id: str, chapter_id: str, db: Session = Depends(get_db)):
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    return db.query(ChapterVersion).filter(
        ChapterVersion.chapter_id == chapter_id
    ).order_by(ChapterVersion.created_at.desc()).all()


@router.get("/{chapter_id}/versions/{version_id}", response_model=ChapterVersionDetailOut)
def get_version(
    project_id: str,
    chapter_id: str,
    version_id: str,
    db: Session = Depends(get_db),
):
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



@router.get("/{chapter_id}/changelog", response_model=List[CharacterChangeLogOut])
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
