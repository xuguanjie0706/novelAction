"""
写章前情节锁定表：由上章成稿 + 章节索引 + 本章章纲确定性生成。

在 pre_write_warning 之前调用，作为硬事实注入主编审稿与写前简报；
与 draft_continuity_bridge 共用节拍收集与 hook 倒带检测。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Chapter, ChapterIndex, OutlineNode
from app.routers.ai.text_utils import plain_text, strip_tail_meta_lines
from app.services.ai.context_assembler import _build_prev_tail
from app.utils.chapter_numbering import display_chapter_number

# 上章若已出现左列语义，本章 hook 禁止再以右列「重开」
_REWIND_PAIRS: list[tuple[str, str]] = [
    ("觉醒", r"觉醒|重组|淬体|苏醒|异变初启"),
    ("休妻", r"休书|休妻|退婚书|写下.*休"),
    ("黑火", r"黑火|神火|九幽|岩浆|火焰涌出"),
    ("突破", r"突破|破境|节节攀升|冲破.*桎梏"),
    ("击杀", r"轰杀|斩杀|毙命|跪地求饶"),
    ("药老", r"药老|老夫|戒指|老师.*?(苏醒|醒来|还要躲)"),
]

_REWIND_HOOK_MARKERS = re.compile(
    r"觉醒|重组|剧痛|淬体|再度|再次|刚刚开始|初显|异变|苏醒|醒来"
)


def _text_blob(*parts: str) -> str:
    return "\n".join(p for p in parts if (p or "").strip())


def detect_hook_rewind_risk(
    prev_beats: list[str],
    prev_tail: str,
    prev_ending_hook: str,
    current_hook: str,
) -> str | None:
    """规则检测：本章开篇 hook 是否在要求「重播」上章已完成节拍。"""
    corpus = _text_blob(prev_ending_hook, prev_tail, "；".join(prev_beats))
    if not corpus.strip() or not (current_hook or "").strip():
        return None
    if not _REWIND_HOOK_MARKERS.search(current_hook):
        return None
    hits: list[str] = []
    for done_key, rewind_pat in _REWIND_PAIRS:
        if done_key in corpus and re.search(rewind_pat, current_hook):
            hits.append(done_key)
    if not hits:
        return None
    return (
        f"章纲开篇钩子疑似要求重播上章已完成的节拍（{'、'.join(hits)}）。"
        "本章开头必须紧接上章末尾**下一拍**，用「核心事件」推进新动作，"
        "不得把 hook 当作倒叙重开同一场景。"
    )


# 上章语料已出现左列语义时，本章章纲 foreshadow/hook 不得再以右列「重开」
_FORESHADOW_CONFLICT_RULES: list[tuple[str, list[str], str]] = [
    ("药老已交流", ["药老", "老夫", "戒指", "老师"], r"药老|老夫|戒指|老师.*?(苏醒|醒来|初醒|还要躲|意识开始|初次)"),
    ("休妻已完成", ["休书", "休妻", "休了你", "反向退婚"], r"休书|休妻|退婚书|写下.*休|撕.*退婚"),
    ("觉醒已完成", ["觉醒", "斗帝意志", "位格压制"], r"觉醒|重组|淬体|再度觉醒|异变初启"),
]


def _fmt_index_item(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return (
            item.get("note")
            or item.get("beat")
            or item.get("event")
            or item.get("description")
            or ""
        ).strip()
    return str(item).strip() if item else ""


def collect_locked_beats(
    prev_idx: ChapterIndex | None,
    prev_outline: OutlineNode | None,
) -> list[str]:
    """从上章章节索引与章纲提取已锁定节拍（供桥接块与锁定表共用）。"""
    beats: list[str] = []
    if prev_idx:
        for ev in (prev_idx.core_events or [])[:8]:
            text = _fmt_index_item(ev)
            if text:
                beats.append(text)
        if (prev_idx.ending_hook or "").strip():
            beats.append(f"章末状态：{(prev_idx.ending_hook or '').strip()}")
    if prev_outline:
        extra = prev_outline.extra if isinstance(prev_outline.extra, dict) else {}
        end_hook = (extra.get("end_hook") or prev_outline.highlight or "").strip()
        if end_hook:
            beats.append(f"大纲章末：{end_hook}")
    return beats


def _outline_end_hook(outline_node: OutlineNode | None) -> str:
    if not outline_node:
        return ""
    extra = outline_node.extra if isinstance(outline_node.extra, dict) else {}
    return (extra.get("end_hook") or outline_node.highlight or "").strip()


def _current_outline_foreshadow(outline_node: OutlineNode | None) -> str:
    if not outline_node:
        return ""
    extra = outline_node.extra if isinstance(outline_node.extra, dict) else {}
    return (extra.get("foreshadow") or "").strip()


def _detect_foreshadow_conflicts(corpus: str, foreshadow: str) -> list[dict[str, str]]:
    if not corpus.strip() or not foreshadow.strip():
        return []
    conflicts: list[dict[str, str]] = []
    for label, done_markers, rewind_pat in _FORESHADOW_CONFLICT_RULES:
        if not any(m in corpus for m in done_markers):
            continue
        if re.search(rewind_pat, foreshadow):
            conflicts.append({
                "field": "foreshadow",
                "outline_text": foreshadow[:300],
                "reason": (
                    f"上章已成稿/索引已含「{label}」，本章章纲伏笔仍要求类似情节，"
                    "禁止倒带重播，须改章纲或开篇承接下一拍。"
                ),
            })
    return conflicts


def _build_forbidden_replays(
    locked_beats: list[str],
    outline_conflicts: list[dict[str, str]],
    hook_warn: str | None,
) -> list[str]:
    forbidden: list[str] = []
    for c in outline_conflicts:
        reason = c.get("reason", "")
        if reason and reason not in forbidden:
            forbidden.append(reason)
    if hook_warn:
        forbidden.append(hook_warn)
    corpus = "；".join(locked_beats)
    if any(k in corpus for k in ("药老", "老夫", "戒指")):
        forbidden.append(
            "禁止再次描写药老/戒指「初次苏醒、还要躲到什么时候」式首次现身；"
            "须承接上章已有对话或结盟下一拍。"
        )
    if any(k in corpus for k in ("休书", "休妻")):
        forbidden.append("禁止再次口头休妻/写休书/撕退婚书（上章已完成）。")
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for item in forbidden:
        key = item[:80]
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out[:8]


def format_lock_table_prompt_block(lock: dict[str, Any]) -> str:
    """格式化为注入 pre_write_warning 的文本块。"""
    if not lock.get("has_prev"):
        return "（第一章，无上章锁定节拍）"
    lines = [
        f"▍上章已锁定（第{lock.get('prev_chapter_number')}章 → 第{lock.get('current_chapter_number')}章，"
        "以下事实不可倒带，优先级高于本章章纲 foreshadow/hook 字面）",
    ]
    for i, b in enumerate(lock.get("locked_beats") or [], 1):
        lines.append(f"  {i}. {b[:220]}")
    anchor = (lock.get("prev_tail_anchor") or "").strip()
    if anchor:
        lines.append(f"▍上章正文末尾锚点（开篇须接下一瞬间）\n「{anchor}」")
    forbidden = lock.get("forbidden_replays") or []
    if forbidden:
        lines.append("▍本章禁止重播")
        for f in forbidden:
            lines.append(f"  · {f}")
    conflicts = lock.get("outline_conflicts") or []
    if conflicts:
        lines.append("▍章纲冲突（须消化后再写，不得照抄冲突 foreshadow）")
        for c in conflicts:
            lines.append(f"  · [{c.get('field')}] {c.get('reason', '')}")
    return "\n".join(lines)


def build_chapter_lock_table(
    db: Session,
    project_id: str,
    chapter: Chapter,
) -> dict[str, Any]:
    """
    生成写章前锁定表（无 LLM）。

    Returns:
        dict 含 locked_beats / forbidden_replays / outline_conflicts /
        prev_tail_anchor / prompt_block / has_prev 等。
    """
    cur_no = display_chapter_number(chapter.title, chapter.sort_order)
    prev_chapter = (
        db.query(Chapter)
        .filter(
            Chapter.project_id == project_id,
            Chapter.sort_order < (chapter.sort_order or 0),
            Chapter.deleted_at.is_(None),
        )
        .order_by(Chapter.sort_order.desc())
        .first()
    )
    if not prev_chapter:
        empty: dict[str, Any] = {
            "has_prev": False,
            "prev_chapter_number": None,
            "current_chapter_number": cur_no,
            "locked_beats": [],
            "forbidden_replays": [],
            "outline_conflicts": [],
            "prev_tail_anchor": "",
            "hook_rewind_warning": None,
            "prompt_block": format_lock_table_prompt_block({"has_prev": False}),
        }
        return empty

    prev_no = display_chapter_number(prev_chapter.title, prev_chapter.sort_order)
    prev_tail = _build_prev_tail(prev_chapter)
    prev_idx = (
        db.query(ChapterIndex)
        .filter(
            ChapterIndex.project_id == project_id,
            ChapterIndex.chapter_id == prev_chapter.id,
        )
        .first()
    )
    prev_outline: OutlineNode | None = None
    if prev_chapter.outline_node_id:
        prev_outline = db.query(OutlineNode).filter(
            OutlineNode.id == prev_chapter.outline_node_id
        ).first()

    locked_beats = collect_locked_beats(prev_idx, prev_outline)
    corpus = "\n".join(locked_beats) + "\n" + (prev_tail or "")
    prev_ending = (prev_idx.ending_hook if prev_idx else "") or _outline_end_hook(prev_outline)

    outline_node: OutlineNode | None = None
    if chapter.outline_node_id:
        outline_node = db.query(OutlineNode).filter(
            OutlineNode.id == chapter.outline_node_id
        ).first()

    cur_hook = (outline_node.hook if outline_node else "") or ""
    foreshadow = _current_outline_foreshadow(outline_node)
    hook_warn = detect_hook_rewind_risk(locked_beats, prev_tail, prev_ending, cur_hook)
    outline_conflicts = _detect_foreshadow_conflicts(corpus, foreshadow)
    if hook_warn and not any(c.get("field") == "hook" for c in outline_conflicts):
        outline_conflicts.append({
            "field": "hook",
            "outline_text": cur_hook[:300],
            "reason": hook_warn,
        })

    forbidden_replays = _build_forbidden_replays(locked_beats, outline_conflicts, hook_warn)
    anchor = ""
    if prev_tail:
        clean = strip_tail_meta_lines(prev_tail)
        anchor = clean[-200:] if len(clean) > 200 else clean

    lock: dict[str, Any] = {
        "has_prev": True,
        "prev_chapter_number": prev_no,
        "current_chapter_number": cur_no,
        "locked_beats": locked_beats,
        "forbidden_replays": forbidden_replays,
        "outline_conflicts": outline_conflicts,
        "prev_tail_anchor": anchor,
        "hook_rewind_warning": hook_warn,
    }
    lock["prompt_block"] = format_lock_table_prompt_block(lock)
    return lock


def merge_lock_table_into_warn_result(warn_result: dict, lock: dict[str, Any]) -> dict:
    """将锁定表并入预警结果，并把章纲冲突提升为 risks。"""
    out = dict(warn_result)
    out["chapter_lock_table"] = {
        "has_prev": lock.get("has_prev", False),
        "prev_chapter_number": lock.get("prev_chapter_number"),
        "current_chapter_number": lock.get("current_chapter_number"),
        "locked_beats": lock.get("locked_beats") or [],
        "forbidden_replays": lock.get("forbidden_replays") or [],
        "outline_conflicts": lock.get("outline_conflicts") or [],
        "prev_tail_anchor": lock.get("prev_tail_anchor") or "",
    }
    risks = list(out.get("risks") or [])
    existing_desc = {str(r.get("description", ""))[:120] for r in risks if isinstance(r, dict)}
    for c in lock.get("outline_conflicts") or []:
        desc = c.get("reason", "")
        if not desc or desc[:120] in existing_desc:
            continue
        risks.insert(
            0,
            {
                "type": "continuity",
                "severity": "critical",
                "description": desc,
                "suggested_fix": (
                    "以锁定表与上章末尾为准修改开篇/必发事件；"
                    "勿按冲突 foreshadow 倒带重播。"
                ),
            },
        )
        existing_desc.add(desc[:120])
    out["risks"] = risks[:15]
    out["risk_count"] = len(out["risks"])
    if any(r.get("severity") in ("high", "critical") for r in out["risks"] if isinstance(r, dict)):
        out["ok"] = False
    return out
