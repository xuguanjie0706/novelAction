"""
写章跨章桥接：上章锁定状态、禁止情节倒带、章纲 hook 冲突预警、主角语风锚点。

由 ``draft_ctx_bridge.resolve_draft_bridge_context``（``assemble_full`` 调用）注入 ``draft_bridge_context``，
与 ``prev_chapter_tail`` 互补：尾部锚点管「语势」，本模块管「时间线不得回卷」。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Chapter, ChapterIndex, Character, OutlineNode, Project
from app.services.ai.narrative_knowledge import build_knowledge_boundary_lines
from app.utils.chapter_numbering import display_chapter_number

# 上章若已出现左列语义，本章 hook/开篇禁止再以右列语义「重新演一遍」
_REWIND_PAIRS: list[tuple[str, str]] = [
    ("觉醒", r"觉醒|重组|淬体|苏醒|异变初启"),
    ("休妻", r"休书|休妻|退婚书|写下.*休"),
    ("黑火", r"黑火|神火|九幽|岩浆|火焰涌出"),
    ("突破", r"突破|破境|节节攀升|冲破.*桎梏"),
    ("击杀", r"轰杀|斩杀|毙命|跪地求饶"),
]

_REWIND_HOOK_MARKERS = re.compile(
    r"觉醒|重组|剧痛|淬体|再度|再次|刚刚开始|初显|异变"
)


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


def _load_prev_index(
    db: Session, project_id: str, prev_chapter: Chapter | None
) -> ChapterIndex | None:
    if not prev_chapter:
        return None
    return (
        db.query(ChapterIndex)
        .filter(
            ChapterIndex.project_id == project_id,
            ChapterIndex.chapter_id == prev_chapter.id,
        )
        .first()
    )


def _outline_end_hook(outline_node: OutlineNode | None) -> str:
    if not outline_node:
        return ""
    extra = outline_node.extra if isinstance(outline_node.extra, dict) else {}
    return (extra.get("end_hook") or outline_node.highlight or "").strip()


def _locked_beats(
    prev_idx: ChapterIndex | None,
    prev_outline: OutlineNode | None,
) -> list[str]:
    beats: list[str] = []
    if prev_idx:
        for ev in (prev_idx.core_events or [])[:8]:
            text = _fmt_index_item(ev)
            if text:
                beats.append(text)
        if (prev_idx.ending_hook or "").strip():
            beats.append(f"章末状态：{(prev_idx.ending_hook or '').strip()}")
    end_from_outline = _outline_end_hook(prev_outline)
    if end_from_outline:
        beats.append(f"大纲章末：{end_from_outline}")
    return beats


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


def _protagonist_voice_block(db: Session, project_id: str) -> str:
    chars = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.role)
        .all()
    )
    lead: Character | None = None
    for c in chars:
        if c.role == "protagonist":
            lead = c
            break
    if not lead:
        for c in chars:
            notes = (c.author_notes or "") + (c.personality or "")
            if "主角" in notes:
                lead = c
                break
    if not lead:
        return ""
    lines = [
        "▍主角语风锚点（跨章不得跳档）",
        f"· 人物：{lead.name}",
    ]
    if lead.personality:
        lines.append(f"· 性格基线：{(lead.personality or '')[:120]}")
    if lead.speech_style:
        lines.append(f"· 说话风格：{(lead.speech_style or '')[:120]}")
    if lead.values:
        lines.append(f"· 价值观：{(lead.values or '')[:100]}")
    kit = lead.speech_kit if isinstance(lead.speech_kit, dict) else {}
    sig = [str(w) for w in (kit.get("signature_words") or []) if w][:5]
    if sig:
        lines.append("· 标志词：" + "、".join(sig))
    samples = [str(s) for s in (kit.get("sample_dialogues") or []) if s][-2:]
    if samples:
        lines.append("· 近期台词样本：「" + "」｜「".join(samples) + "」")
    lines.append(
        "· 硬规则：不得在无剧情台阶的情况下从「压抑隐忍」跳到「癫狂咆哮」或反向崩塌；"
        "情绪升级须由上一章末尾事件触发，语气变化用动作/短句体现。"
    )
    return "\n".join(lines)


def build_draft_continuity_bridge_block(
    db: Session,
    project_id: str,
    chapter: Chapter,
    project: Project,
    outline_node: OutlineNode | None,
    prev_chapter: Chapter | None,
    prev_tail: str,
) -> str:
    """
    组装写章专用跨章桥接块（纯文本，注入 draft prompt）。

    Args:
        prev_tail: 上章正文末尾（已由 assembler 截断），用于与章末钩子对账。
    """
    if not prev_chapter:
        return ""

    prev_idx = _load_prev_index(db, project_id, prev_chapter)
    prev_num = display_chapter_number(prev_chapter.title, prev_chapter.sort_order)
    prev_outline: OutlineNode | None = None
    if prev_chapter.outline_node_id:
        prev_outline = db.query(OutlineNode).filter(
            OutlineNode.id == prev_chapter.outline_node_id
        ).first()

    beats = _locked_beats(prev_idx, prev_outline)
    prev_ending = (prev_idx.ending_hook if prev_idx else "") or _outline_end_hook(prev_outline)

    sections: list[str] = [
        f"▍跨章桥接·第{prev_num}章 → 第{display_chapter_number(chapter.title, chapter.sort_order)}章",
        "▍上章已发生（时间线已锁定，禁止倒带重播）",
    ]
    if beats:
        for i, b in enumerate(beats[:10], 1):
            sections.append(f"  {i}. {b[:200]}")
    else:
        tail_hint = (prev_tail or "").strip()[-400:]
        if tail_hint:
            sections.append(f"  （无章节索引，以下为上章末尾事实锚点）\n  …{tail_hint}")
        else:
            sections.append("  （上章无索引且无正文尾部，仅按章纲推进）")

    sections.append(
        "▍禁止事项\n"
        "· 不得把上表任一节拍当作「本章刚开始」再写一遍（例如上章已觉醒/已口头休妻，"
        "本章不得再写经脉重组、再度觉醒、重新撕退婚书等）。\n"
        "· 本章开头约 200 字须紧接上章正文最后一幕的**下一瞬间**，"
        "承接未决动作（谁拔剑、谁开口、火是否已涌出），禁止无交代跳场或倒叙复盘。\n"
        "· 若章纲「开篇钩子」与上章已完情节冲突，以**上章末尾 + 核心事件**为准推进，"
        "hook 仅作情绪参考，不得据此倒带。"
    )

    cur_hook = (outline_node.hook if outline_node else "") or ""
    rewind_warn = detect_hook_rewind_risk(beats, prev_tail, prev_ending, cur_hook)
    if rewind_warn:
        sections.append(f"▍⚠️ 章纲 hook 冲突预警\n· {rewind_warn}")

    cur_summary = (outline_node.summary if outline_node else "") or ""
    if cur_summary.strip():
        sections.append(f"▍本章应推进的新节拍（来自章纲核心事件）\n· {cur_summary.strip()[:400]}")

    voice = _protagonist_voice_block(db, project_id)
    if voice:
        sections.append(voice)

    sections.extend(build_knowledge_boundary_lines(project))

    # 风格守门（反 AI 腔套话去重 + 章级情绪预算）作为同类「跨章硬约束」聚合进桥接块，
    # 避免改动已冻结的 context_assembler.py（见登记册 600 行红线）。纯统计，无额外 LLM。
    from app.services.ai.draft_style_guard import build_draft_style_guard_block

    style_guard = build_draft_style_guard_block(db, project_id, chapter, outline_node)
    if style_guard:
        sections.append(style_guard)

    return "\n\n".join(sections)
