"""章节路由辅助函数：字数统计、派生数据清理、场景绑定等。

本模块纯函数，不含任何路由装饰器，可被 chapters.py / chapter_version_routes.py 共同导入。
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import (
    Character,
    CharacterChangeLog,
    Chapter,
    ChapterDebriefApplyRecord,
    ChapterDebriefCache,
    ChapterDebriefUndo,
    ChapterIndex,
    Foreshadow,
    MemoryChunk,
    QualityDebt,
    ReaderPromise,
    Scene,
    StoryLine,
)


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
    if not text:
        return 0
    decoded = html.unescape(text)
    clean = re.sub(r"<[^>]+>", "", decoded)
    cjk = len(re.findall(r"[一-鿿㐀-䶿\U00020000-\U0002a6df]", clean))
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

    Args:
        db: 数据库会话。
        project_id: 项目 ID。
        chapter_id: 章节 ID。
        with_quality_debts: False 用于「改稿/重写」清缓存：不碰质量债务行；
                            True 将本章关联债务标为已修复并解除 chapter_id（不删行）。
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
    """整章重写（replace_existing）或删章前调用：清掉本章旧稿派生数据。

    处理顺序：
    1. 从 undo 快照回滚覆盖型字段（character realm/location/status/realm_rank、storyline status）
    2. 按 chapter_id 精确清除追加型数据（storyline beats、character known_skills/owned_items）
    3. 清除 realm_milestones 快照中本章记录
    4. 清除记忆 / ChapterIndex / 复盘缓存 / 伏笔 / 读者承诺 / 复盘变更日志（不删质量债务行）
    5. 删除 undo 快照行
    """
    # ── 1. 回滚覆盖型字段 ─────────────────────────────────────────────────────
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

    # ── 2. 清除追加型数据（beats / skills / items）────────────────────────────
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
        # ── 3. 清除 realm_milestones 中本章记录 ──────────────────────────────
        if isinstance(char.extra, dict) and char.extra.get("debrief_realm_milestones"):
            milestones = char.extra["debrief_realm_milestones"]
            cleaned_ms = [
                m for m in milestones
                if not (isinstance(m, dict) and m.get("chapter_id") == chapter_id)
            ]
            if len(cleaned_ms) != len(milestones):
                char.extra = {**char.extra, "debrief_realm_milestones": cleaned_ms}
                changed = True

    # ── 4. 清除记忆 / ChapterIndex / 复盘缓存 / 伏笔 ─────────────────────────
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

    # ── 4b. 读者承诺：本章埋下的删除；本章兑现的回退为 open ───────────────────
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

    # ── 4c. 本章复盘审计日志 ──────────────────────────────────────────────────
    db.query(CharacterChangeLog).filter(
        CharacterChangeLog.project_id == project_id,
        CharacterChangeLog.chapter_id == chapter_id,
        CharacterChangeLog.source == "debrief",
    ).delete(synchronize_session=False)

    # ── 5. 删除 undo 快照 ─────────────────────────────────────────────────────
    if undo:
        db.delete(undo)


def normalize_chapter_sort_orders(db: Session, project_id: str) -> None:
    """统一章节排序为连续整数，避免历史数据出现重复/空洞 sort_order 导致前端显示错乱。
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


def bind_scenes_to_chapter(db: Session, project_id: str, chapter: "object") -> int:
    """将大纲节点关联的 Scene 记录绑定到已写完的章节，并更新 Scene 状态。

    绑定条件：
    - `chapter.outline_node_id` 存在
    - Scene.chapter_id 为 null（避免重复绑定）

    副作用：
    - Scene.chapter_id = chapter.id
    - Scene.status: "planned" → "written"

    Returns:
        实际绑定的 Scene 数量；outline_node_id 缺失时返回 0。
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


def build_scene_writing_outline(scenes: list) -> dict:
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
