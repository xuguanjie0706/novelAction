"""
draft_graph/quality_helper.py — 章节质检上下文组装与 AI 调用辅助。

职责：
  提供 run_quality_check() 函数，供 quality_check 节点调用。
  逻辑与 gated_draft_routes._run_quality_check_inline 一致，
  但接受 draft_content 参数（允许质检尚未写库的草稿）。

此模块仅依赖 models / services/ai，不依赖 routers，保持层次正确。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc

from app.database import SessionLocal
from app.models import Chapter, Character, MemoryChunk, StoryLine, WorldSetting

if TYPE_CHECKING:
    from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


async def run_quality_check(
    db: Session,
    project_id: str,
    chapter_id: str,
    draft_content: str,
    chapter_title: str,
    svc: "AIService",
) -> dict:
    """
    组装质检上下文并调用 AIService.quality_check，将结果写回 Chapter 记录。

    接受 draft_content 参数，允许质检尚未正式写库的草稿（save_commit 之前）。
    调用成功后将 overall_score / last_quality_report 写入 Chapter 并 commit。

    @param db: 活跃的 SQLAlchemy Session
    @param project_id: 项目 UUID 字符串
    @param chapter_id: 章节 UUID 字符串
    @param draft_content: 待质检的正文（来自 graph state，非 DB）
    @param chapter_title: 章节标题
    @param svc: 已初始化的 AIService 实例
    @returns quality_check 返回的 dict（含 overall_score / dimensions / suggestions）
    @raises Exception: AI 调用失败时向上抛出
    """
    from app.routers.ai.normalization import format_world_setting_context
    from app.routers.ai.quality_debt import sync_quality_debts

    # ── 组装质检上下文 ─────────────────────────────────────────────────────
    memories = (
        db.query(MemoryChunk)
        .filter(MemoryChunk.project_id == project_id)
        .limit(50)
        .all()
    )
    settings_list = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id
    ).all()
    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()

    character_states = [
        f"{c.name}：境界={c.current_realm or '未知'}，"
        f"位置={c.current_location or '未知'}，"
        f"状态={c.current_status or 'alive'}"
        for c in characters[:20]
    ]

    storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id
    ).all()
    storylines_context = [
        f"{s.name}：{s.description or ''}"
        for s in storylines[:10]
    ]

    check_types = [
        "plot", "character", "setting_consistency",
        "pacing", "hooks", "outline_alignment",
    ]

    # ── AI 质检 ────────────────────────────────────────────────────────────
    report = await svc.quality_check(
        chapter_content=draft_content,
        chapter_title=chapter_title,
        memories=[m.content for m in memories],
        settings_summary=[
            format_world_setting_context(s, content_limit=260)
            for s in settings_list[:20]
        ],
        check_types=check_types,
        character_states=character_states,
        storylines_context=storylines_context,
    )

    # ── 写回 Chapter 质检元信息 ────────────────────────────────────────────
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if chapter and isinstance(report, dict):
        chapter.last_quality_score = report.get("overall_score")
        chapter.last_quality_report = report
        chapter.quality_checked_at = sqlfunc.now()
        try:
            sync_quality_debts(db, project_id, chapter, report)
            db.commit()
        except Exception:
            logger.warning("sync_quality_debts failed (non-fatal), report still returned")
            db.rollback()

    return report
