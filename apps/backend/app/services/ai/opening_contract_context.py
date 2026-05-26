"""开局承诺（opening_contract）写章 / 章纲展开 prompt 块。

Step 12 产物存于 Project.extra.opening_contract；本模块负责按章号裁剪注入，
并强调与卷一骨架、上章情节、章纲摘要的因果衔接（禁止通用模板空话）。
"""
from __future__ import annotations

OPENING_CHAPTER_MAX = 10

_MILESTONE_LABELS: dict[str, str] = {
    "first_200_words_test": "第1章前200字核验",
    "chapter1_hook": "第1章末钩子",
    "chapter3_payoff": "第3章小爽点",
    "chapter5_foreshadow": "第5章长线伏笔",
    "chapter10_subscribe_reason": "第10章订阅钩",
    "chapter_rhythm": "前10章节奏",
    "opening_traps_to_avoid": "开局避坑",
}


def is_opening_contract_window(volume_index: int, chapter_number: int) -> bool:
    """第一卷且章序在 1–10 内时启用开局承诺注入。"""
    return volume_index == 0 and 1 <= chapter_number <= OPENING_CHAPTER_MAX


def _fmt_traps(traps: object) -> str:
    if isinstance(traps, list):
        items = [str(t).strip() for t in traps if str(t).strip()]
        return "；".join(items) if items else "（未设定）"
    return str(traps).strip() or "（未设定）"


def _chapter_draft_directives(chapter_number: int) -> list[str]:
    """按章号返回写章硬约束（与 Step 12 里程碑对齐）。"""
    lines: list[str] = []
    if chapter_number == 1:
        lines.append(
            "本章开篇前200字必须完成「前200字核验」中的全部事项；"
            "章末必须落实「第1章末钩子」，让读者带着具体问题翻页。"
        )
    elif chapter_number == 2:
        lines.append(
            "承接第1章末钩子抛出的问题，本章不得回避或一笔带过；"
            "障碍升级，但仍保留读者想知道的核心悬念。"
        )
    elif chapter_number == 3:
        lines.append(
            "本章必须交付「第3章小爽点」——主角的第一次具体反转/胜利/资源，"
            "用具体行动与结果呈现，禁止「隐隐感觉变强」式敷衍。"
        )
    elif chapter_number == 4:
        lines.append(
            "爽点后短暂收束并加压，为第5章伏笔做铺垫；"
            "不得用纯日常过渡章消耗读者耐心。"
        )
    elif chapter_number == 5:
        lines.append(
            "本章必须埋下「第5章长线伏笔」，具体到人物/秘密/物件，"
            "且与卷一核心冲突或核心谜题有可见关联。"
        )
    elif 6 <= chapter_number <= 9:
        lines.append(
            f"按「前10章节奏」推进至第10章订阅钩，本章须推进至少一条故事线"
            f"或兑现一个小承诺，避免空转。"
        )
    elif chapter_number == 10:
        lines.append(
            "本章末尾必须落实「第10章订阅钩」——给出读者无法放下、"
            "必须看第11章的具体悬念（强敌/秘密/关系逆转等，须落到具体事件）。"
        )
    return lines


def _continuity_clause(
    *,
    prev_chapter_tail: str = "",
    outline_summary: str = "",
    plot_anchor: str = "",
) -> str:
    parts: list[str] = [
        "▍情节衔接硬约束",
        "开局承诺中的事件/人物/秘密必须与本卷已设定情节同一条因果链，"
        "禁止另起炉灶或与上章状态矛盾。",
    ]
    if plot_anchor.strip():
        parts.append(f"卷一骨架锚点：{plot_anchor.strip()[:400]}")
    if outline_summary.strip():
        parts.append(f"本章章纲核心事件：{outline_summary.strip()[:200]}")
    if prev_chapter_tail.strip():
        tail = prev_chapter_tail.strip()
        parts.append(
            f"上章结尾状态（必须承接）：…{tail[-500:] if len(tail) > 500 else tail}"
        )
    else:
        parts.append("（首章无上章正文；须与卷一摘要/核心冲突自然衔接。）")
    return "\n".join(parts)


def build_opening_contract_draft_block(
    contract: dict,
    chapter_number: int,
    *,
    prev_chapter_tail: str = "",
    outline_summary: str = "",
    vol1_summary: str = "",
    vol1_conflict: str = "",
) -> str:
    """写正文路径：第一卷 1–10 章注入裁剪后的开局承诺 + 衔接约束。"""
    if not contract or not isinstance(contract, dict):
        return ""

    plot_anchor = " ".join(
        filter(None, [
            vol1_summary.strip(),
            f"核心冲突：{vol1_conflict.strip()}" if vol1_conflict.strip() else "",
        ])
    )

    lines: list[str] = [
        "【开局追读承诺 · 写章硬约束（Step 12，必须与本卷情节同链兑现）】",
        _continuity_clause(
            prev_chapter_tail=prev_chapter_tail,
            outline_summary=outline_summary,
            plot_anchor=plot_anchor,
        ),
    ]
    lines.extend(_chapter_draft_directives(chapter_number))

    rhythm = (contract.get("chapter_rhythm") or "").strip()
    if rhythm:
        lines.append(f"前10章节奏：{rhythm}")

    traps = _fmt_traps(contract.get("opening_traps_to_avoid"))
    lines.append(f"必须避开的开局坑：{traps}")

    lines.append("▍里程碑原文（兑现时须用到已出场人物/地点/势力名，勿写口号）")
    for key, label in _MILESTONE_LABELS.items():
        if key in ("chapter_rhythm", "opening_traps_to_avoid"):
            continue
        val = contract.get(key)
        if not val:
            continue
        if key == "first_200_words_test" and chapter_number != 1:
            continue
        if key == "chapter10_subscribe_reason" and chapter_number < 8:
            continue
        lines.append(f"  · {label}：{val}")

    lines.append(
        "兑现方式：在正文行动/对话/事件中落实，不要作者旁白解释；"
        "与 ReaderPromise 台账一致，复盘会自动检测。"
    )
    return "\n".join(lines)


def build_opening_contract_expand_block(
    contract: dict,
    batch_start: int,
    batch_end: int,
    *,
    vol1_summary: str = "",
    vol1_conflict: str = "",
    vol1_hook: str = "",
) -> str:
    """章纲展开路径：第一卷批次与 1–10 章重叠时注入完整开局承诺块。"""
    if not contract or not isinstance(contract, dict):
        return ""
    if batch_start > OPENING_CHAPTER_MAX:
        return ""

    effective_end = min(batch_end, OPENING_CHAPTER_MAX)
    lines: list[str] = [
        "\n【开局追读承诺 · 章纲必须对齐（Step 12，禁止通用模板钩子）】",
        "以下承诺已在 Bootstrap 定稿；本批章纲的 opening_hook / end_hook / "
        "core_event / promise_fulfilled 必须逐条呼应，且用到卷内已有人物与冲突。",
    ]
    if vol1_summary.strip():
        lines.append(f"卷一摘要：{vol1_summary.strip()[:300]}")
    if vol1_conflict.strip():
        lines.append(f"卷一核心冲突：{vol1_conflict.strip()[:200]}")
    if vol1_hook.strip():
        lines.append(f"卷末悬念种子：{vol1_hook.strip()[:150]}")

    for key, label in _MILESTONE_LABELS.items():
        val = contract.get(key)
        if not val:
            continue
        if key == "opening_traps_to_avoid":
            lines.append(f"  · {label}：{_fmt_traps(val)}")
        else:
            lines.append(f"  · {label}：{val}")

    batch_directives: list[str] = []
    for ch in range(batch_start, effective_end + 1):
        batch_directives.extend(_chapter_draft_directives(ch))
    if batch_directives:
        seen: set[str] = set()
        unique = []
        for d in batch_directives:
            if d not in seen:
                seen.add(d)
                unique.append(d)
        lines.append("▍本批章节编辑指令")
        lines.extend(f"  - {d}" for d in unique)

    lines.append(
        "  ⚠️ 第1章 opening_hook 须满足 first_200_words_test；"
        "第1/3/5/10章 end_hook 须分别兑现对应里程碑；"
        "promise_fulfilled 字段填写已兑现承诺的关键短语（2字以上）。"
    )
    return "\n".join(lines)


def append_opening_contract_draft_brief(
    db: object,
    project: object,
    chapter: object,
    outline_node: object | None,
    volume_index: int,
    prev_chapter_tail: str,
    writing_brief_context: str,
) -> str:
    """第一卷 1–10 章写正文：将开局承诺块追加到 writing_brief_context。"""
    from app.services.bootstrap.opening_contract_io import resolve_opening_contract

    ch_no = getattr(chapter, "sort_order", None) or 0
    if not is_opening_contract_window(volume_index, ch_no):
        return writing_brief_context

    contract = resolve_opening_contract(db, project, heal=False)  # type: ignore[arg-type]
    if not contract:
        return writing_brief_context

    vol_node = None
    parent_id = getattr(outline_node, "parent_id", None) if outline_node else None
    if parent_id:
        from app.models import OutlineNode

        vol_node = db.query(OutlineNode).filter(  # type: ignore[union-attr]
            OutlineNode.id == parent_id,
        ).first()

    block = build_opening_contract_draft_block(
        contract,
        ch_no,
        prev_chapter_tail=prev_chapter_tail,
        outline_summary=(outline_node.summary or "") if outline_node else "",
        vol1_summary=(vol_node.summary or "") if vol_node else "",
        vol1_conflict=(vol_node.conflict or "") if vol_node else "",
    )
    if block:
        return writing_brief_context + "\n\n" + block
    return writing_brief_context
