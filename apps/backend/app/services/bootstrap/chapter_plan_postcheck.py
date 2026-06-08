"""章纲懒展开：生成后确定性自检（与 linter CH-04 对齐，命中则定向重试本批）。"""
from __future__ import annotations

from app.services.outline_linter.event_ledger import CharacterRef
from app.services.outline_linter.helpers import is_placeholder
from app.services.bootstrap.life_ledger_expand import (
    build_life_violation_hint,
    detect_intra_batch_life_violations,
)


def detect_empty_choice_costs(
    batch_data: list,
    *,
    batch_start: int,
) -> list[int]:
    """返回 ``choice_cost`` 为空或占位的卷内章号列表。"""
    gaps: list[int] = []
    for i, item in enumerate(batch_data):
        if not isinstance(item, dict):
            continue
        ch = item.get("chapter_number")
        if isinstance(ch, int) and ch > 0:
            ch_num = ch
        else:
            ch_num = batch_start + i
        if is_placeholder((item.get("choice_cost") or "").strip()):
            gaps.append(ch_num)
    return gaps


def build_choice_cost_violation_hint(chapter_numbers: list[int]) -> str:
    """把 CH-04 类漏填拼成「重输出本批」的定向修正提示。"""
    if not chapter_numbers:
        return ""
    nums = "、".join(str(n) for n in sorted(chapter_numbers))
    return (
        "\n【⚠️ 上一轮本批 choice_cost 未填，必须修正后重输出整批 JSON】\n"
        f"  · 第 {nums} 章的 choice_cost 为空或仅占位——这是最高优先级字段，"
        "每章须写本章 protagonist_choice 带来的具体损失/风险（伤势、暴露、债务、誓言等），"
        "供下一章 opening_hook 承接。\n"
        "  · 禁止空字符串、「无」「待定」等占位；格式示例："
        "「答应了陆青云的条件，但被迫交出了令牌，下章须面对监视者」。\n"
        "  重输出前逐章核对：上述章号的 choice_cost 均已填写且≥10字。"
    )


def build_batch_postcheck_retry_hint(
    batch_data: list,
    *,
    batch_start: int,
    char_refs: list[CharacterRef],
    dead_before: dict[str, tuple[str, int]],
    volume_start_global: int,
) -> tuple[str, list[tuple], list[int]]:
    """章数正确后跑 LIFE + CH-04 自检。

    Returns:
        (定向修正提示, life_violations, cost_gap_chapters) —— 提示非空表示应重试本批。
    """
    life_violations = detect_intra_batch_life_violations(
        batch_data,
        batch_start=batch_start,
        char_refs=char_refs,
        dead_before=dead_before,
        volume_start_global=volume_start_global,
    )
    cost_gaps = detect_empty_choice_costs(batch_data, batch_start=batch_start)
    if not life_violations and not cost_gaps:
        return "", life_violations, cost_gaps
    hints: list[str] = []
    if life_violations:
        hints.append(build_life_violation_hint(life_violations))
    if cost_gaps:
        hints.append(build_choice_cost_violation_hint(cost_gaps))
    return "".join(hints), life_violations, cost_gaps
