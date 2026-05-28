"""AI 扩写/前几卷上下文：节点→章纲、伏笔账本、逾期伏笔、已生成章节窗口。"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import Foreshadow, OutlineNode
from app.services.outline_planning import TARGET_WORDS_PER_CHAPTER
from app.utils.chapter_numbering import display_chapter_number

from app.routers.outline.helpers.text_utils import _clean_outline_text

def _outline_node_to_chapter_context(node: OutlineNode) -> dict:
    title_text = str(node.title or "")
    match = re.match(r"第(\d+)章[:：]\s*(.*)", title_text)
    number = display_chapter_number(title_text, getattr(node, "sort_order", None))
    title = match.group(2).strip() if match else title_text
    extra = node.extra if isinstance(node.extra, dict) else {}
    return {
        "number": number,
        "title": title or "未命名",
        "core_event": node.summary or "",
        "opening_hook": node.hook or "",
        "character_change": node.conflict or "",
        # 实力里程碑常单独写突破/境界，需并入成长轨迹扫描
        "power_milestone": getattr(node, "power_milestone", None) or "",
        "foreshadow": extra.get("foreshadow", ""),
        "end_hook": extra.get("end_hook") or node.highlight or "",
        "protagonist_want": extra.get("protagonist_want", ""),
        "protagonist_obstacle": extra.get("protagonist_obstacle", ""),
        "protagonist_choice": extra.get("protagonist_choice", ""),
        "choice_cost": extra.get("choice_cost", ""),
        "villain_action": extra.get("villain_action", ""),
        "pacing": extra.get("pacing", "medium"),
        "word_estimate": extra.get("word_estimate", TARGET_WORDS_PER_CHAPTER),
    }


def _anchor_volume_for_expand(node: OutlineNode, id_map: dict) -> OutlineNode | None:
    """从当前展开节点向上找到所属卷（用于判断「前几卷」范围）。"""
    cur: OutlineNode | None = node
    seen: set = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        if getattr(cur, "node_type", None) == "volume":
            return cur
        pid = cur.parent_id
        if not pid:
            return None
        cur = id_map.get(pid)
    return None


def _chapter_plan_root_volume(node: OutlineNode, id_map: dict) -> OutlineNode | None:
    """章节计划所属根卷（parent 链上第一个 volume）。"""
    cur: OutlineNode | None = node
    seen: set = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        if getattr(cur, "node_type", None) == "volume":
            return cur
        if not cur.parent_id:
            return None
        cur = id_map.get(cur.parent_id)
    return None


def _prior_volume_chapter_plan_nodes(
    all_nodes: list[OutlineNode],
    id_map: dict,
    anchor_volume: OutlineNode,
) -> list[OutlineNode]:
    """严格早于 anchor 卷的根卷下，所有已落库的 chapter_plan。"""
    anchor_order = anchor_volume.sort_order or 0
    out: list[OutlineNode] = []
    for n in all_nodes:
        if getattr(n, "node_type", None) != "chapter_plan":
            continue
        root = _chapter_plan_root_volume(n, id_map)
        if root is None or getattr(root, "node_type", None) != "volume":
            continue
        if (root.sort_order or 0) < anchor_order:
            out.append(n)
    return out


def _sort_chapter_plan_nodes(nodes: list[OutlineNode]) -> list[OutlineNode]:
    def sort_key(n: OutlineNode):
        ctx = _outline_node_to_chapter_context(n)
        num = ctx.get("number")
        try:
            inum = int(num) if num is not None else 0
        except (TypeError, ValueError):
            inum = 0
        return (inum, str(n.id))

    return sorted(nodes, key=sort_key)


def _compact_prior_volume_plot_lines(
    chapters_ctx: list[dict],
    *,
    core_lim: int,
    hook_lim: int,
    fs_lim: int,
) -> list[str]:
    lines: list[str] = []
    for ch in chapters_ctx:
        num = ch.get("number") if ch.get("number") is not None else "?"
        title = _clean_outline_text(ch.get("title"), 48)
        core = _clean_outline_text(ch.get("core_event"), core_lim)
        hook = _clean_outline_text(ch.get("end_hook"), hook_lim)
        fs = _clean_outline_text(ch.get("foreshadow"), fs_lim)
        line = f"第{num}章《{title}》| 核心：{core} | 章末：{hook}"
        if fs:
            line += f" | 伏笔：{fs}"
        lines.append(line)
    return lines


def _format_prior_volumes_plot_context(chapters_ctx: list[dict], max_chars: int) -> str:
    """前几卷章纲情节链：优先保留全部章节，通过缩短字段适配 token；仍过长则截断并提示。"""
    if not chapters_ctx or max_chars < 120:
        return ""
    for core_lim, hook_lim, fs_lim in ((90, 72, 72), (60, 48, 48), (42, 36, 36), (28, 24, 24)):
        lines = _compact_prior_volume_plot_lines(
            chapters_ctx, core_lim=core_lim, hook_lim=hook_lim, fs_lim=fs_lim
        )
        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text
    return text[: max_chars - 24] + "\n…（前几卷情节链过长已截断）"


def _build_prior_foreshadow_ledger(
    chapters_ctx: list[dict],
    foreshadow_rows: list[Foreshadow],
    max_chars: int,
) -> str:
    """章纲五要素中的伏笔行 + 伏笔表中仍未回收的条目。"""
    if max_chars < 80:
        return ""
    parts: list[str] = []
    used: set[str] = set()
    ch_lines: list[str] = []
    for ch in chapters_ctx:
        raw = (ch.get("foreshadow") or "").strip()
        if not raw:
            continue
        key = raw[:240]
        if key in used:
            continue
        used.add(key)
        num = ch.get("number") if ch.get("number") is not None else "?"
        ch_lines.append(f"第{num}章：{raw}")
    if ch_lines:
        parts.append("【来自前几卷章纲五要素】\n" + "\n".join(ch_lines))

    db_lines: list[str] = []
    open_rows = [f for f in foreshadow_rows if (f.status or "open") == "open"]
    open_rows.sort(key=lambda f: (-(f.priority or 3), str(f.id)))
    for f in open_rows:
        code = f.code or "—"
        title = _clean_outline_text(f.title, 80)
        desc = _clean_outline_text(f.description, 140)
        plan = f.planned_resolve_chapter
        plan_s = f"预计第{plan}章回收" if plan else "回收章未定"
        db_lines.append(f"{code} {title} | {plan_s} | {desc}")
    if db_lines:
        parts.append("【伏笔表（仍未回收）】\n" + "\n".join(db_lines))

    text = "\n\n".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…（伏笔台账过长已截断）"
    return text


def _build_overdue_foreshadow_ledger(
    foreshadow_rows: list,
    max_chapter_number: int,
    max_chars: int = 2000,
) -> str:
    """
    从伏笔表中筛选「已逾期未回收」条目并格式化为字符串。
    逾期定义：status=open AND planned_resolve_chapter <= max_chapter_number
    """
    if not foreshadow_rows or max_chapter_number <= 0:
        return ""
    overdue = [
        f for f in foreshadow_rows
        if (f.status or "open") == "open"
        and f.planned_resolve_chapter
        and f.planned_resolve_chapter <= max_chapter_number
    ]
    if not overdue:
        return ""
    overdue.sort(key=lambda f: (-(f.priority or 3), f.planned_resolve_chapter or 0))
    lines: list[str] = []
    for f in overdue:
        code = f.code or "—"
        title = _clean_outline_text(f.title, 60)
        plan = f.planned_resolve_chapter
        desc = _clean_outline_text(f.description, 100)
        lines.append(f"{code} {title} | 应于第{plan}章前回收（已逾期） | {desc}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…（逾期列表过长已截断）"
    return text


def _ai_expand_prior_plot_budget(_model_profile: str) -> int:
    return 14000


def _ai_expand_prior_foreshadow_budget(_model_profile: str) -> int:
    return 8000


def _load_existing_chapter_context(
    db: Session,
    project_id: str,
    limit: int = 24,
) -> list[dict]:
    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
    ).all()
    chapters = [_outline_node_to_chapter_context(node) for node in nodes]
    chapters.sort(key=lambda chapter: chapter.get("number") or 0)
    return chapters[-limit:]
