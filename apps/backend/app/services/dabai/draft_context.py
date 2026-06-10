"""dabai 写章上下文组装 — 向量记忆 + 近章剧情 + 人物状态（图谱优先，DB 兜底）。

设计目标：解决「正文衔接差」——旧版写章只注入金手指+五拍+上章尾巴 400 字，
pgvector 记忆与 Neo4j 图谱完全没接入。本模块统一产出四个注入块：

1. graph_block      主角当前境界/位置/行踪/敌对（Neo4j，最新事实）
2. recent_plot_block 近 N 章剧情一句话摘要 + 上章末钩子（承接硬约束）
3. memory_block     pgvector 语义检索（以本章五拍要素为 query，落 RagRetrievalLog）
4. char_state_block 本章出场人物（witnesses）当前状态（图谱 → Character 表兜底）

降级原则：任一数据源不可用（无 Neo4j / 无 embedding / 无记忆）→ 对应块为空字符串，
绝不阻塞写章主链路。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Chapter, Character, MemoryChunk, OutlineNode, Project
from app.services.dabai.neo4j_sync import (
    build_graph_context_block,
    fetch_character_states,
)
from app.services.dabai.outline_plan import chapter_display_number

logger = logging.getLogger(__name__)

RECENT_PLOT_CHAPTERS = 3      # 近章摘要条数
MEMORY_TOP_K = 8              # 语义召回条数
MEMORY_RECENCY = 4            # 时序锚定条数
MAX_WITNESS_STATES = 6        # 出场人物状态最多注入人数


@dataclass
class DabaiDraftContext:
    """写章 prompt 注入块集合（均为已格式化字符串，空串表示该源无内容）。"""

    graph_block: str = ""
    recent_plot_block: str = ""
    memory_block: str = ""
    char_state_block: str = ""
    rag_snapshot: dict | None = field(default=None)  # SSE 透出用（rag_context 事件）


def _plain(text: str | None, limit: int = 0) -> str:
    t = re.sub(r"<[^>]+>", "", text or "").strip()
    return t[:limit] if limit and len(t) > limit else t


def resolve_protagonist_name(db: Session, project: Project) -> str:
    """主角真实姓名：Character.role=protagonist 优先；找不到返回空串（图谱块降级）。"""
    row = (
        db.query(Character.name)
        .filter(Character.project_id == project.id, Character.role == "protagonist")
        .order_by(Character.created_at.asc())
        .first()
    )
    return (row[0] or "").strip() if row else ""


def _beat(plan: OutlineNode | None) -> dict:
    extra = (plan.extra if plan else {}) or {}
    dabai = extra.get("dabai") or {}
    return dabai if isinstance(dabai, dict) else {}


def _witness_names(plan: OutlineNode | None) -> list[str]:
    ws = _beat(plan).get("witnesses") or []
    if not isinstance(ws, list):
        ws = [str(ws)]
    return [str(w).strip() for w in ws if str(w).strip()][:MAX_WITNESS_STATES]


# ──────────────────────── 近章剧情摘要 ────────────────────────

def _chapter_one_liner(db: Session, project_id: str, ch: Chapter) -> str:
    """单章一句话摘要：复盘记忆（最重要 1 条）优先 → 章纲 summary → 正文头。"""
    n = chapter_display_number(ch)
    mem = (
        db.query(MemoryChunk)
        .filter(
            MemoryChunk.project_id == project_id,
            MemoryChunk.chapter_id == ch.id,
        )
        .order_by(MemoryChunk.importance_score.desc())
        .first()
    )
    if mem and mem.content:
        return _plain(mem.content, 90)
    if ch.outline_node and ch.outline_node.summary:
        return _plain(ch.outline_node.summary, 90)
    return _plain(ch.content, 80)


def build_recent_plot_block(db: Session, project_id: str, chapter: Chapter) -> str:
    """近 N 章剧情摘要 + 上章末钩子（开头承接的硬约束来源）。"""
    cur_order = int(chapter.sort_order or 0)
    if cur_order <= 0:
        return ""
    prevs: list[Chapter] = (
        db.query(Chapter)
        .filter(
            Chapter.project_id == project_id,
            Chapter.sort_order < cur_order,
            Chapter.deleted_at.is_(None),
            Chapter.content.isnot(None),
            Chapter.content != "",
        )
        .order_by(Chapter.sort_order.desc())
        .limit(RECENT_PLOT_CHAPTERS)
        .all()
    )
    if not prevs:
        return ""
    lines = ["【前情提要（近章剧情，禁止与之矛盾）】"]
    for ch in reversed(prevs):  # 按时间正序展示
        one = _chapter_one_liner(db, project_id, ch)
        if one:
            lines.append(f"- 第{chapter_display_number(ch)}章《{_plain(ch.title, 30)}》：{one}")
    hook = ""
    node = prevs[0].outline_node
    if node:
        hook = (node.hook or node.highlight or "").strip()
    if hook:
        lines.append(f"- 上章末钩子（本章开头必须正面承接）：{_plain(hook, 80)}")
    return "\n".join(lines) if len(lines) > 1 else ""


# ──────────────────────── 出场人物状态 ────────────────────────

def build_char_state_block(
    db: Session,
    project: Project,
    plan: OutlineNode | None,
    protagonist: str,
) -> str:
    """本章出场人物（见证者/被打脸者）当前状态：图谱最新事实优先，Character 表兜底。"""
    names = [n for n in _witness_names(plan) if n != protagonist]
    if not names:
        return ""
    graph_states = fetch_character_states(str(project.id), names)
    db_rows = {
        c.name: c
        for c in db.query(Character)
        .filter(Character.project_id == project.id, Character.name.in_(names))
        .all()
    }
    lines: list[str] = []
    for name in names:
        parts: list[str] = []
        gs = graph_states.get(name)
        row = db_rows.get(name)
        rank = (gs or {}).get("realm_rank")
        if rank is None and row and row.realm_rank is not None:
            rank = row.realm_rank
        if rank is not None:
            parts.append(f"境界档第{rank}档")
        loc = None
        if gs and gs.get("moves"):
            loc = gs["moves"][0].get("loc")
        if not loc and row and row.current_location:
            loc = row.current_location
        if loc:
            parts.append(f"位置：{loc}")
        if gs and protagonist and protagonist in (gs.get("enemies") or []):
            parts.append("与主角敌对")
        if row and row.current_status and row.current_status != "alive":
            parts.append(f"状态：{row.current_status}")
        if parts:
            lines.append(f"- {name}：{'；'.join(parts)}")
    if not lines:
        return ""
    return "【本章出场人物当前状态（以此为准）】\n" + "\n".join(lines)


# ──────────────────────── 向量记忆检索 ────────────────────────

def _memory_query_text(chapter: Chapter, plan: OutlineNode | None) -> str:
    beat = _beat(plan)
    parts = [
        _plain(chapter.title, 40),
        str(beat.get("yaqu_setup") or ""),
        str(beat.get("yinbao") or ""),
        str(beat.get("shuang_payoff") or ""),
        "、".join(_witness_names(plan)),
    ]
    return " ".join(p for p in parts if p).strip()[:300]


async def build_memory_block(
    db: Session,
    project: Project,
    chapter: Chapter,
    plan: OutlineNode | None,
) -> tuple[str, dict | None]:
    """pgvector 语义检索 + 时序锚定，落 RagRetrievalLog（source=draft_context）。

    Returns:
        (注入块文本, SSE 快照)；检索失败/无记忆时 ("", None)。
    """
    query = _memory_query_text(chapter, plan)
    if not query:
        return "", None
    try:
        from app.services.rag_retrieval_service import retrieve_and_log_draft_context

        max_ch = chapter_display_number(chapter) - 1
        merged, summary, _row, snapshot = await retrieve_and_log_draft_context(
            db,
            project_id=str(project.id),
            chapter_id=str(chapter.id),
            query=query,
            top_k_semantic=MEMORY_TOP_K,
            max_chapter=max_ch if max_ch > 0 else None,
            recency_limit=MEMORY_RECENCY,
            commit=False,
        )
        if not merged or not summary.strip():
            return "", snapshot
        return "【相关记忆（语义检索，可呼应/禁矛盾）】\n" + summary.strip(), snapshot
    except Exception as exc:
        logger.warning("dabai 记忆检索降级 project=%s: %s", project.id, exc)
        return "", None


# ──────────────────────── 编排入口 ────────────────────────

async def build_dabai_draft_context(
    db: Session,
    project: Project,
    chapter: Chapter,
    plan: OutlineNode | None,
) -> DabaiDraftContext:
    """组装全部注入块；任何一块失败只降级该块，不抛出。"""
    ctx = DabaiDraftContext()
    protagonist = ""
    try:
        protagonist = resolve_protagonist_name(db, project)
        if protagonist:
            ctx.graph_block = build_graph_context_block(str(project.id), protagonist)
    except Exception as exc:
        logger.warning("dabai 图谱块降级 project=%s: %s", project.id, exc)
    try:
        ctx.recent_plot_block = build_recent_plot_block(db, str(project.id), chapter)
    except Exception as exc:
        logger.warning("dabai 前情块降级 project=%s: %s", project.id, exc)
    try:
        ctx.char_state_block = build_char_state_block(db, project, plan, protagonist)
    except Exception as exc:
        logger.warning("dabai 人物状态块降级 project=%s: %s", project.id, exc)
    try:
        ctx.memory_block, ctx.rag_snapshot = await build_memory_block(db, project, chapter, plan)
    except Exception as exc:
        logger.warning("dabai 记忆块降级 project=%s: %s", project.id, exc)
    return ctx
