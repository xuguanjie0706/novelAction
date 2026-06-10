"""dabai 实验书架（dabai_* 表）写章上下文 — 前情/上章结尾/记忆回灌/线索回灌。

与精品文 ``draft_context`` 隔离：只读 dabai_* 表，不依赖 Project/Chapter/图谱/pgvector。
记忆与线索回灌是复盘台账的「读端」：没有回灌，复盘提取的事实对写作模型不可见。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiClue, DabaiMemory

_MEM_LABELS = {
    "summary": "摘要", "fact": "事实", "event": "事件",
    "state": "状态", "relation": "关系",
}


@dataclass
class LabDraftContext:
    """实验书架写章前置上下文。"""

    prev_tail: str
    recent_plot_block: str
    memory_block: str = ""   # 复盘记忆回灌（重要度+时效 Top-K）
    clue_block: str = ""     # 未回收线索回灌（埋设越久越优先）


def _tail_of_content(content: str, max_len: int = 800) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    return text[-max_len:] if len(text) > max_len else text


def _build_memory_block(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline, top_k: int = 8,
) -> str:
    """重要度优先 + 同分按时效取 Top-K 记忆，展示按章号升序。"""
    rows = (
        db.query(DabaiMemory)
        .filter(
            DabaiMemory.project_id == project.id,
            DabaiMemory.chapter_number < ch.chapter_number,
        )
        .order_by(DabaiMemory.importance.desc(), DabaiMemory.chapter_number.desc())
        .limit(top_k)
        .all()
    )
    if not rows:
        return ""
    lines = [
        f"  - 第{m.chapter_number}章[{_MEM_LABELS.get(m.mem_type, m.mem_type)}] {m.content}"
        for m in sorted(rows, key=lambda m: (m.chapter_number or 0))
    ]
    return "【既定事实记忆（复盘提取，不可违背）】\n" + "\n".join(lines)


def _build_clue_block(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline, top_k: int = 8,
) -> str:
    """未回收线索按埋设章号升序（埋得越久越优先提醒回收）。"""
    rows = (
        db.query(DabaiClue)
        .filter(
            DabaiClue.project_id == project.id,
            DabaiClue.status == "open",
            DabaiClue.chapter_planted < ch.chapter_number,
        )
        .order_by(DabaiClue.chapter_planted)
        .limit(top_k)
        .all()
    )
    if not rows:
        return ""
    lines = [
        f"  - 《{c.title}》第{c.chapter_planted}章埋设：{(c.description or '')[:60]}"
        for c in rows
    ]
    return (
        "【未回收线索（埋设越久越优先；本章可自然推进或回收，禁止凭空冒出与之矛盾的设定）】\n"
        + "\n".join(lines)
    )


def build_lab_draft_context(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
) -> LabDraftContext:
    """组装上章结尾 + 近章前情块 + 记忆/线索回灌块（仅基于 dabai_* 表）。"""
    prev_tail = ""
    if (ch.chapter_number or 0) > 1:
        prev = (
            db.query(DabaiChapterOutline)
            .filter(
                DabaiChapterOutline.project_id == project.id,
                DabaiChapterOutline.chapter_number == ch.chapter_number - 1,
            )
            .first()
        )
        if prev and (prev.content or "").strip():
            prev_tail = _tail_of_content(prev.content or "", 800)

    recent_lines: list[str] = []
    written = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project.id,
            DabaiChapterOutline.chapter_number < ch.chapter_number,
            DabaiChapterOutline.content.isnot(None),
        )
        .order_by(DabaiChapterOutline.chapter_number.desc())
        .limit(3)
        .all()
    )
    for row in reversed(written):
        snippet = _tail_of_content(row.content or "", 120)
        hook = (row.end_hook or "").strip()
        line = f"  第{row.chapter_number}章《{row.title or ''}》"
        if hook:
            line += f"；末钩：{hook}"
        if snippet:
            line += f"；收束：…{snippet}"
        recent_lines.append(line)

    recent_plot_block = ""
    if recent_lines:
        recent_plot_block = "【前情提要（已发生事实，不可推翻）】\n" + "\n".join(recent_lines)

    return LabDraftContext(
        prev_tail=prev_tail,
        recent_plot_block=recent_plot_block,
        memory_block=_build_memory_block(db, project, ch),
        clue_block=_build_clue_block(db, project, ch),
    )
