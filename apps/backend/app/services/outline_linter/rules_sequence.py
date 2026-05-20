"""章间 linter 规则（SEQ-*）。"""

from __future__ import annotations

from app.services.outline_linter.helpers import ChapterSnapshot, text_overlap
from app.services.outline_linter.schemas import LinterIssue


def lint_sequence(
    chapters: list[ChapterSnapshot],
    *,
    volume_phase: str,
    planned_chapters: int,
) -> list[LinterIssue]:
    if len(chapters) < 2:
        return []

    issues: list[LinterIssue] = []
    phase = (volume_phase or "rising").lower()
    planned = planned_chapters or len(chapters)
    climax_exempt_start = max(1, planned - 4)

    for i in range(1, len(chapters)):
        prev, cur = chapters[i - 1], chapters[i]
        prev_cost = prev.ex_str("choice_cost")
        if len(prev_cost) >= 10:
            hook = (cur.hook or "").strip()
            summary = (cur.summary or "").strip()
            if not text_overlap(prev_cost, hook) and not text_overlap(prev_cost, summary):
                issues.append(LinterIssue(
                    rule_id="SEQ-01",
                    severity="high",
                    scope="sequence",
                    message=(
                        f"第{cur.chapter_number}章未承接第{prev.chapter_number}章 choice_cost"
                    ),
                    suggestion="改 opening_hook 或上章 choice_cost，体现后遗症",
                    field="hook",
                    chapter_number_in_volume=cur.chapter_number,
                    node_id=cur.id,
                ))

        if cur.chapter_number == 31 and len(prev_cost) >= 10:
            if not text_overlap(prev_cost, (cur.hook or "")):
                issues.append(LinterIssue(
                    rule_id="SEQ-07",
                    severity="critical",
                    scope="sequence",
                    message="第31章（第二批首章）未承接第30章代价",
                    suggestion="懒展开第二批首章必须硬承接前批末尾",
                    field="hook",
                    chapter_number_in_volume=31,
                    node_id=cur.id,
                ))

    # SEQ-02: 主线连续独占（简化：storyline_ids 完全相同且连续 >=3）
    if phase != "climax":
        streak = 1
        prev_sl: tuple[str, ...] | None = None
        streak_start = 1
        for ch in chapters:
            sl = tuple(sorted(str(x) for x in ch.storyline_ids))
            if len(sl) != 1:
                streak = 1
                prev_sl = None
                continue
            if sl == prev_sl and prev_sl:
                streak += 1
            else:
                streak = 1
                streak_start = ch.chapter_number
                prev_sl = sl
            if streak >= 3 and ch.chapter_number < climax_exempt_start:
                issues.append(LinterIssue(
                    rule_id="SEQ-02",
                    severity="medium",
                    scope="sequence",
                    message=f"第{streak_start}～{ch.chapter_number}章仅推进同一条故事线（连续{streak}章）",
                    suggestion="插入支线或感情线章节",
                    field="storyline_ids",
                    chapter_number_in_volume=ch.chapter_number,
                ))
                streak = 1
                prev_sl = None

    if phase == "dark_hour":
        fast_run = 0
        for ch in chapters:
            if (ch.pacing or "normal").lower() == "fast":
                fast_run += 1
                if fast_run >= 3:
                    issues.append(LinterIssue(
                        rule_id="SEQ-03",
                        severity="high",
                        scope="sequence",
                        message=f"dark_hour 卷第{ch.chapter_number}章起连续{fast_run}章 pacing=fast",
                        suggestion="至暗期不宜连续快节奏",
                        field="pacing",
                        chapter_number_in_volume=ch.chapter_number,
                        node_id=ch.id,
                    ))
                    break
            else:
                fast_run = 0

        beat_count = sum(
            1 for ch in chapters if (ch.extra or {}).get("has_emotional_beat")
        )
        if chapters and beat_count / len(chapters) < 0.4:
            issues.append(LinterIssue(
                rule_id="SEQ-04",
                severity="high",
                scope="sequence",
                message=(
                    f"dark_hour 卷情感章占比 {beat_count}/{len(chapters)} "
                    f"低于 40%"
                ),
                suggestion="增加 has_emotional_beat=true 的章节",
            ))

    return issues


def _signature_text(ch: ChapterSnapshot) -> str:
    parts = [
        ch.summary or "",
        ch.conflict or "",
        ch.end_hook_text(),
        ch.ex_str("protagonist_choice"),
    ]
    return " ".join(p for p in parts if p).strip()


def _jaccard_similarity(a: str, b: str, n: int = 3) -> float:
    def grams(s: str) -> set[str]:
        s = "".join(s.split())
        if len(s) < n:
            return {s} if s else set()
        return {s[i : i + n] for i in range(len(s) - n + 1)}

    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def lint_semantic_duplicates(
    chapters: list[ChapterSnapshot],
    *,
    threshold: float = 0.88,
    window: int = 12,
) -> list[LinterIssue]:
    """SEQ-05：章节摘要+钩子语义同质化（同步 Jaccard，无 embedding 依赖）。"""
    if len(chapters) < 2:
        return []

    issues: list[LinterIssue] = []
    sorted_ch = sorted(chapters, key=lambda c: c.chapter_number)
    seen: set[tuple[int, int]] = set()

    for i, a in enumerate(sorted_ch):
        text_a = _signature_text(a)
        if len(text_a) < 20:
            continue
        for b in sorted_ch[i + 1 :]:
            if b.chapter_number - a.chapter_number > window:
                break
            pair = (a.chapter_number, b.chapter_number)
            if pair in seen:
                continue
            sim = _jaccard_similarity(text_a, _signature_text(b))
            if sim >= threshold:
                seen.add(pair)
                severity = "high" if sim >= 0.92 else "medium"
                issues.append(LinterIssue(
                    rule_id="SEQ-05",
                    severity=severity,
                    scope="sequence",
                    message=(
                        f"第{a.chapter_number}章与第{b.chapter_number}章梗概高度相似"
                        f"（Jaccard≈{sim:.2f}）"
                    ),
                    suggestion="改写其中一章的核心事件或章末钩子，拉开差异",
                    chapter_number_in_volume=b.chapter_number,
                    node_id=b.id,
                ))
    return issues
