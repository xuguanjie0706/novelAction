"""
draft_ctx_promise.py — ReaderPromise 写章注入 + hook_strength 趋势预警

职责：
- 查询当前章节覆盖窗口内 open 状态的读者承诺，格式化为写章约束文本
- hook_strength 趋势预警：连续低钩时追加主编强制指令
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ChapterIndex, ReaderPromise


# ═══════════════════════════════════════════════════════════════
# hook_strength 趋势预警辅助
# ═══════════════════════════════════════════════════════════════

def append_hook_trend_warning(
    db: Session, project_id: str, current_sort_order: int,
    writing_brief_context: str, window: int = 5, threshold: float = 3.0,
) -> str:
    """
    查询本章之前最近 ``window`` 章的 hook_strength 均值，若低于 ``threshold``
    则向 writing_brief_context 追加主编强制钩子指令。

    @returns 追加预警后的 writing_brief_context；未触发时原样返回
    """
    if current_sort_order <= 0:
        return writing_brief_context

    recent = (
        db.query(ChapterIndex.hook_strength)
        .filter(
            ChapterIndex.project_id == project_id,
            ChapterIndex.chapter_number < current_sort_order,
            ChapterIndex.hook_strength.isnot(None),
        )
        .order_by(ChapterIndex.chapter_number.desc())
        .limit(window)
        .all()
    )
    if len(recent) < 3:
        return writing_brief_context

    avg = sum(r[0] for r in recent) / len(recent)
    if avg >= threshold:
        return writing_brief_context

    warning = (
        f"\n\n▍【钩子趋势预警 · 主编强制指令】\n"
        f"近 {len(recent)} 章 hook_strength 均值 {avg:.1f}/5（连续偏弱），读者续读意愿存在系统性风险。\n"
        "本章章末钩子升级为最高优先级硬约束：\n"
        "· 必须选用悬念揭示型（A）或格局颠覆反转型（C）钩子，禁止以心理独白、景色描写或总结句收尾\n"
        "· 最后一段 ≤ 80 字，用一个具体的、尚未解决的行动/对话节点结束，不要解释、不要抒情\n"
        "· 该章整体须含 ≥ 1 处可被读者截图传播的「高光瞬间」以对冲前期低钩章带来的读者疲劳"
    )
    return writing_brief_context + warning


# ═══════════════════════════════════════════════════════════════
# ReaderPromise 写章注入辅助
# ═══════════════════════════════════════════════════════════════

def build_reader_promise_context(
    db: Session, project_id: str, chapter_sort_order: int, lookahead: int = 5,
) -> str:
    """
    查询当前章节覆盖窗口内 open 状态的读者承诺，格式化为写章约束文本。

    分两级：
    - 必须兑现：承诺截止章号 ≤ 当前 sort_order（已到期）
    - 可以兑现：截止章号在 [当前+1, 当前+lookahead] 内

    @returns 格式化文本；无匹配承诺时返回空字符串。
    """
    open_promises: list[ReaderPromise] = (
        db.query(ReaderPromise)
        .filter(
            ReaderPromise.project_id == project_id,
            ReaderPromise.status == "open",
        )
        .order_by(ReaderPromise.priority.desc())
        .limit(40)
        .all()
    )
    if not open_promises:
        return ""

    must_fulfill: list[ReaderPromise] = []
    can_fulfill: list[ReaderPromise] = []

    for p in open_promises:
        if p.expected_chapter_window is not None:
            src = p.source_chapter_number or 0
            deadline = src + p.expected_chapter_window
        else:
            deadline = None

        if deadline is not None and deadline <= chapter_sort_order:
            must_fulfill.append(p)
        elif deadline is not None and chapter_sort_order < deadline <= chapter_sort_order + lookahead:
            can_fulfill.append(p)
        elif deadline is None and (p.priority or 3) >= 4:
            can_fulfill.append(p)

    if not must_fulfill and not can_fulfill:
        return ""

    type_zh = {
        "chapter_ending": "章末预告", "volume_ending": "卷末预告",
        "name_implication": "名字/称号暗示",
        "chapter_comment_consensus": "章评共识",
        "protagonist_claim": "主角宣言",
    }

    def _fmt(p: ReaderPromise, show_deadline: bool = False) -> str:
        ptype = type_zh.get(p.promise_type or "", p.promise_type or "承诺")
        stars = "⭐" * min(max(p.priority or 3, 1), 5)
        line = f"  [{ptype} {stars}] {p.promise_text}"
        if show_deadline and p.expected_chapter_window is not None:
            src = p.source_chapter_number or 0
            line += f"  （截止第 {src + p.expected_chapter_window} 章）"
        return line

    lines: list[str] = ["【读者承诺台账（写章时必须对照）】"]
    if must_fulfill:
        lines.append(f"⚠️  本章【必须兑现】的承诺（共 {len(must_fulfill)} 条，已到期）：")
        for p in must_fulfill:
            lines.append(_fmt(p, show_deadline=True))
    if can_fulfill:
        lines.append(f"💡  本章【可以兑现】的承诺（共 {len(can_fulfill)} 条，即将到期或高优先级）：")
        for p in can_fulfill:
            lines.append(_fmt(p, show_deadline=True))
    lines.append(
        "兑现要求：在正文中以具体行动/对话/事件落实承诺，不要口号式敷衍；"
        "复盘环节会自动检测兑现情况并更新承诺状态，不需要在正文里追加任何标注。"
    )
    return "\n".join(lines)
