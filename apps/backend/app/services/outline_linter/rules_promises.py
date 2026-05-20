"""读者承诺 linter（RP-*）。"""

from __future__ import annotations

from typing import Any

from app.services.outline_linter.chapter_index import build_global_chapter_index
from app.services.outline_linter.helpers import ChapterSnapshot, text_overlap
from app.services.outline_linter.schemas import LinterIssue


def promise_fulfilled_in_window(
    fulfilled_by_global: dict[int, str],
    promise_text: str,
    source_chapter: int,
    window: int,
) -> bool:
    """承诺窗口 [source+1, source+window] 内是否已有 promise_fulfilled 命中原文。"""
    if not source_chapter or not window or not promise_text.strip():
        return False
    for g in range(source_chapter + 1, source_chapter + window + 1):
        pf = fulfilled_by_global.get(g, "")
        if pf and text_overlap(pf, promise_text, min_len=2):
            return True
    return False


def _merge_volume_fulfilled_index(
    fulfilled_by_global: dict[int, str],
    chapters: list[ChapterSnapshot],
    volume_start_global: int,
) -> None:
    """将当前卷待落库章纲的 promise_fulfilled 并入全书索引（同 session flush 后亦需兜底）。"""
    for ch in chapters:
        pf = ch.ex_str("promise_fulfilled")
        if not pf:
            continue
        g = volume_start_global + ch.sort_order
        fulfilled_by_global[g] = pf


def lint_reader_promises(
    db: Any,
    project_id: Any,
    chapters: list[ChapterSnapshot],
    *,
    volume_start_global: int,
) -> list[LinterIssue]:
    """检查 ReaderPromise 与章纲 promise_fulfilled 对齐。"""
    from app.models import OutlineNode, ReaderPromise

    issues: list[LinterIssue] = []
    _, max_global = build_global_chapter_index(db, project_id)

    open_rows = (
        db.query(ReaderPromise)
        .filter(
            ReaderPromise.project_id == project_id,
            ReaderPromise.status == "open",
        )
        .all()
    )
    if not open_rows:
        return issues

    # 全书章纲 promise_fulfilled 索引
    all_plans = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "chapter_plan",
        )
        .all()
    )
    node_to_global, _ = build_global_chapter_index(db, project_id)
    fulfilled_by_global: dict[int, str] = {}
    for node in all_plans:
        g = node_to_global.get(str(node.id))
        if g is None:
            continue
        pf = ((node.extra or {}).get("promise_fulfilled") or "").strip()
        if pf:
            fulfilled_by_global[g] = pf

    _merge_volume_fulfilled_index(fulfilled_by_global, chapters, volume_start_global)
    if chapters:
        vol_max = volume_start_global + max(ch.sort_order for ch in chapters)
        max_global = max(max_global, vol_max)

    vol_globals = {volume_start_global + ch.sort_order for ch in chapters}

    for rp in open_rows:
        priority = int(rp.priority or 3)
        src = int(rp.source_chapter_number or 0)
        window = int(rp.expected_chapter_window or 0)
        text = (rp.promise_text or "").strip()
        if not text:
            continue

        deadline = src + window if src and window else 0
        fulfilled = promise_fulfilled_in_window(
            fulfilled_by_global, text, src, window,
        )

        # 仅当全书已规划越过截止章，且窗口内仍无任何兑现记录时阻断（避免整卷一次生成误杀）
        if (
            priority >= 4
            and deadline
            and max_global > deadline
            and not fulfilled
        ):
            issues.append(LinterIssue(
                rule_id="RP-01",
                severity="critical",
                scope="volume",
                message=(
                    f"读者承诺超窗未兑现（priority={priority}）："
                    f"应在第{deadline}章前兑现，当前已规划至第{max_global}章，"
                    f"窗口内无 promise_fulfilled"
                ),
                suggestion="在章纲中填写 promise_fulfilled 或调整承诺窗口",
            ))

        if priority >= 4 and src and window:
            hit = fulfilled
            window_touches_volume = any(
                src < g <= src + window for g in vol_globals
            )
            if not hit and window_touches_volume:
                issues.append(LinterIssue(
                    rule_id="RP-02",
                    severity="high",
                    scope="volume",
                    message=(
                        f"承诺窗口（第{src+1}～{src+window}章）内无 promise_fulfilled："
                        f"{text[:36]}…"
                    ),
                    suggestion="在对应章 extra.promise_fulfilled 填写兑现片段",
                ))

        for ch in chapters:
            pf = ch.ex_str("promise_fulfilled")
            if not pf or priority < 3:
                continue
            if not text_overlap(pf, text, min_len=2):
                issues.append(LinterIssue(
                    rule_id="RP-03",
                    severity="medium",
                    scope="chapter",
                    message=f"第{ch.chapter_number}章 promise_fulfilled 与承诺原文不匹配",
                    field="extra.promise_fulfilled",
                    chapter_number_in_volume=ch.chapter_number,
                    node_id=ch.id,
                    suggestion="对齐 ReaderPromise 原文关键词",
                ))

    return issues


def lint_opening_contract_rp(
    chapters: list[ChapterSnapshot],
    opening_contract: dict,
) -> list[LinterIssue]:
    """RP-04 / OC-01：开局承诺与第1章钩子。"""
    issues: list[LinterIssue] = []
    if not opening_contract or not chapters:
        return issues

    ch1 = next((c for c in chapters if c.chapter_number == 1), None)
    if not ch1:
        return issues

    hook1 = opening_contract.get("chapter1_hook", "")
    if hook1:
        opening = (ch1.hook or "").strip()
        if opening and not text_overlap(opening, str(hook1), min_len=2):
            issues.append(LinterIssue(
                rule_id="OC-01",
                severity="high",
                scope="chapter",
                message="第1章 opening_hook 未呼应 opening_contract.chapter1_hook",
                field="hook",
                chapter_number_in_volume=1,
                node_id=ch1.id,
                suggestion="对齐开局追读承诺中的第1章钩子",
            ))

    return issues
