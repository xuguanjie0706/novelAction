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
from app.services.ai.chapter_lock_table import collect_locked_beats, detect_hook_rewind_risk
from app.utils.chapter_numbering import display_chapter_number


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

    beats = collect_locked_beats(prev_idx, prev_outline)
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

    realm_target = _realm_axis_bridge_block(db, project_id, chapter)
    if realm_target:
        sections.append(realm_target)

    exc_block = _power_exception_bridge_block(db, project_id)
    if exc_block:
        sections.append(exc_block)

    canon_block = _fanfic_canon_bridge_block(db, project_id)
    if canon_block:
        sections.append(canon_block)

    return "\n\n".join(sections)


def _realm_axis_bridge_block(db: Session, project_id: str, chapter: Any) -> str:
    """写章硬目标：本章主角「应有境界」（方向1 单一权威轴）。无境界体系/无章纲锚点时空。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or chapter is None:
        return ""
    try:
        from app.services.ai.realm_axis import expected_realm_for_chapter

        label, rank = expected_realm_for_chapter(db, project, chapter)
    except Exception:
        return ""
    if not label or rank is None:
        return ""
    return (
        "▍本章主角应有境界（章级境界轴，写章硬目标）\n"
        f"· 本章主角境界应处于「{label}」一线：不得无故落后于此（写成更低境界），"
        "也不得无代价、无过程地跳到更高大境；如确有突破，须在正文交代修炼/机缘过程与代价。"
    )


def _power_exception_bridge_block(db: Session, project_id: str) -> str:
    """写章硬约束：跨境破例预算（方向4）。仅在已登记破例或本书有境界体系时注入，避免无境界书噪声。"""
    from app.models import PowerSystem
    from app.services.ai.power_exception import (
        build_power_exception_block,
        get_power_exception_budget,
    )

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return ""
    has_budget = bool(get_power_exception_budget(project))
    has_power_system = (
        db.query(PowerSystem.id).filter(PowerSystem.project_id == project_id).first() is not None
    )
    if not has_budget and not has_power_system:
        return ""
    block = build_power_exception_block(project)
    return f"▍{block}" if block else ""


def _fanfic_canon_bridge_block(db: Session, project_id: str) -> str:
    """同人书：注入原著不可改事实与 OOC 雷区（纯读库，零 LLM）。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return ""
    extra = project.extra if isinstance(project.extra, dict) else {}
    if not extra.get("fanfic_positioning"):
        return ""
    fp = extra.get("fanfic_positioning") or {}
    canon = extra.get("fanfic_canon") or {}
    dev = extra.get("fanfic_deviation") or {}
    entry = extra.get("fanfic_entry") or {}
    lines = [
        "▍同人·原著约束（正文硬遵守）",
        f"· 原著《{fp.get('source_work_title', '')}》· {fp.get('fanfic_trope_label', '')} · 贴合{fp.get('canon_fidelity', 'medium')}",
    ]
    if dev.get("divergence_point"):
        lines.append(f"· 分歧点：{dev['divergence_point']}（此前须贴原著走向，此后走同人主线）")
    if entry.get("entry_chapter_hint"):
        lines.append(f"· 原著时间锚点：当前进度对应{entry['entry_chapter_hint']}，时间线不得前后矛盾")
    for anc in (canon.get("timeline_anchors") or [])[:3]:
        lines.append(f"· 原著节点：{anc}")
    for fact in (canon.get("immutable_facts") or [])[:5]:
        lines.append(f"· 不可改：{fact}")
    for forb in (dev.get("forbidden_changes") or [])[:4]:
        lines.append(f"· 禁止魔改：{forb}")
    for taboo in (fp.get("ooc_taboos") or [])[:4]:
        lines.append(f"· 雷区：{taboo}")
    lines.append(
        "· 对话须贴合各角色 speech_style；禁止把原著角色写成完全不同的性格而无剧情交代。"
    )
    return "\n".join(lines)
