"""读者承诺 linter（RP-*）。"""

from __future__ import annotations

from typing import Any

from app.services.outline_linter.chapter_index import build_global_chapter_index
from app.services.outline_linter.helpers import ChapterSnapshot, text_overlap
from app.services.outline_linter.schemas import LinterIssue


def _promise_window_label(source_chapter: int, window: int) -> str:
    """读者承诺兑现窗口的人类可读描述（不截断）。"""
    start = source_chapter + 1
    end = source_chapter + window
    if window <= 1:
        return f"第 {start} 章"
    return f"第 {start}～{end} 章"


def _rp03_issues_for_chapters(
    chapters: list[ChapterSnapshot],
    open_promises: list[tuple[str, int]],
) -> list[LinterIssue]:
    """章纲「本章兑现承诺」与读者承诺台账对齐（每章至多 1 条 RP-03）。"""
    texts = [
        (t.strip(), priority)
        for t, priority in open_promises
        if t.strip() and priority >= 3
    ]
    if not texts:
        return []

    issues: list[LinterIssue] = []
    for ch in chapters:
        pf = ch.ex_str("promise_fulfilled")
        if not pf:
            continue
        if any(text_overlap(pf, t, min_len=2) for t, _ in texts):
            continue
        samples = [t for t, _ in texts[:3]]
        sample_hint = "；".join(f"「{s}」" for s in samples if s)
        if len(texts) > 3:
            sample_hint = f"{sample_hint} 等共 {len(texts)} 条" if sample_hint else f"共 {len(texts)} 条未兑现承诺"
        issues.append(LinterIssue(
            rule_id="RP-03",
            severity="medium",
            scope="chapter",
            message=(
                f"第{ch.chapter_number}章「本章兑现承诺」填了「{pf}」，"
                f"与读者承诺台账中未兑现条目均无法对上关键词（需与原文有至少 2 字相同）"
                + (f"。未兑现承诺原文：{sample_hint}" if sample_hint else "")
            ),
            field="extra.promise_fulfilled",
            chapter_number_in_volume=ch.chapter_number,
            node_id=ch.id,
            suggestion=(
                "把章纲里的兑现片段改成某条读者承诺原文里的关键词；"
                "若本章不兑现任何承诺，请留空"
            ),
        ))
    return issues


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

        # RP-01：承诺超窗改为 high 警告（已从 BLOCKING_RULE_IDS 移除）。
        # 设计说明：promise_fulfilled 字段在「写章/复盘」阶段才填写，
        # 章纲规划时永远为空 → 在规划门控里始终误杀，故不再阻断。
        if (
            priority >= 4
            and deadline
            and max_global > deadline
            and not fulfilled
        ):
            issues.append(LinterIssue(
                rule_id="RP-01",
                severity="high",   # 原 critical，已降级
                scope="volume",
                message=(
                    f"高优先级读者承诺超窗未兑现：「{text}」"
                    f"应在第 {deadline} 章前兑现，当前大纲已规划至第 {max_global} 章，"
                    f"承诺窗口内各章「本章兑现承诺」均为空或未对上关键词"
                ),
                suggestion=(
                    "在窗口内某一章的章纲「本章兑现承诺」填入该承诺原文关键词；"
                    "或到「读者承诺」页延长窗口 / 调低优先级"
                ),
            ))

        if priority >= 4 and src and window:
            hit = fulfilled
            window_touches_volume = any(
                src < g <= src + window for g in vol_globals
            )
            if not hit and window_touches_volume:
                win = _promise_window_label(src, window)
                issues.append(LinterIssue(
                    rule_id="RP-02",
                    severity="high",
                    scope="volume",
                    message=(
                        f"读者承诺须在窗口内兑现：「{text}」"
                        f"（窗口：{win}；当前窗口内各章「本章兑现承诺」均未填或未对上关键词）"
                    ),
                    suggestion=(
                        f"在{win}中选一章，"
                        f"在章纲「本章兑现承诺」填入该条承诺原文里的关键词（至少 2 字重叠）"
                    ),
                ))

    open_for_rp03 = [
        ((rp.promise_text or "").strip(), int(rp.priority or 3))
        for rp in open_rows
    ]
    issues.extend(_rp03_issues_for_chapters(chapters, open_for_rp03))

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
                message=(
                    f"第 1 章开篇钩子与开局追读承诺不一致："
                    f"章纲为「{opening}」，承诺要求「{str(hook1).strip()}」"
                ),
                field="hook",
                chapter_number_in_volume=1,
                node_id=ch1.id,
                suggestion="改写第 1 章开篇钩子，使其与开局追读承诺中的关键词呼应",
            ))

    return issues
