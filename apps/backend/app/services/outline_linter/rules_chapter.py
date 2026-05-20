"""章级 linter 规则（CH-*）。"""

from __future__ import annotations

from app.services.outline_linter.helpers import (
    ChapterSnapshot,
    is_placeholder,
    is_vague_end_hook,
)
from app.services.outline_linter.schemas import LinterIssue
from app.services.outline_planning import chapter_word_budget_for_phase

MIN_TEXT_LEN = 8
MIN_HOOK_LEN = 10
MIN_END_HOOK_LEN = 12

VAGUE_POWER_RE = ("突破", "变强", "实力大增", "修为提升")


def lint_chapters(chapters: list[ChapterSnapshot]) -> list[LinterIssue]:
    issues: list[LinterIssue] = []
    for ch in chapters:
        issues.extend(_lint_one(ch))
    return issues


def _issue(
    ch: ChapterSnapshot,
    rule_id: str,
    severity: str,
    message: str,
    *,
    field: str = "",
    suggestion: str = "",
    auto_fixable: bool = False,
) -> LinterIssue:
    return LinterIssue(
        rule_id=rule_id,
        severity=severity,
        scope="chapter",
        message=message,
        suggestion=suggestion,
        field=field,
        chapter_number_in_volume=ch.chapter_number,
        node_id=ch.id,
        auto_fixable=auto_fixable,
    )


def _lint_one(ch: ChapterSnapshot) -> list[LinterIssue]:
    out: list[LinterIssue] = []
    n = ch.chapter_number

    want = ch.ex_str("protagonist_want")
    if len(want) < MIN_TEXT_LEN:
        out.append(_issue(
            ch, "CH-01", "high",
            f"第{n}章 protagonist_want 过短或为空",
            field="extra.protagonist_want",
            suggestion="补写主角主动欲望（要/想/必须/决定…）",
        ))

    obstacle = ch.ex_str("protagonist_obstacle")
    if len(obstacle) < MIN_TEXT_LEN:
        out.append(_issue(
            ch, "CH-02", "high",
            f"第{n}章 protagonist_obstacle 过短或为空",
            field="extra.protagonist_obstacle",
            suggestion="补写具体障碍",
        ))

    choice = ch.ex_str("protagonist_choice")
    if len(choice) < MIN_TEXT_LEN:
        out.append(_issue(
            ch, "CH-03", "high",
            f"第{n}章 protagonist_choice 过短或为空",
            field="extra.protagonist_choice",
            suggestion="补写暴露性格的关键选择",
        ))

    cost = ch.ex_str("choice_cost")
    if is_placeholder(cost):
        out.append(_issue(
            ch, "CH-04", "critical",
            f"第{n}章 choice_cost 为空或占位",
            field="extra.choice_cost",
            suggestion="补写选择代价，供下一章承接",
            auto_fixable=True,
        ))

    hook = (ch.hook or "").strip()
    if len(hook) < MIN_HOOK_LEN:
        out.append(_issue(
            ch, "CH-05", "high",
            f"第{n}章 opening_hook 过短或为空",
            field="hook",
            suggestion="补开篇钩子（前500字手段）",
        ))

    end_hook = ch.end_hook_text()
    if len(end_hook) < MIN_END_HOOK_LEN:
        out.append(_issue(
            ch, "CH-06", "high",
            f"第{n}章 end_hook 过短或为空",
            field="extra.end_hook",
            suggestion="补具体章末手法",
        ))
    elif is_vague_end_hook(end_hook):
        out.append(_issue(
            ch, "CH-07", "medium",
            f"第{n}章 end_hook 过于空泛",
            field="extra.end_hook",
            suggestion="避免「悬念丛生」类废话，改具体画面/信息差",
        ))

    summary = (ch.summary or "").strip()
    if not summary:
        out.append(_issue(
            ch, "CH-08", "critical",
            f"第{n}章 core_event（summary）为空",
            field="summary",
            suggestion="补核心事件",
        ))

    villain = ch.ex_str("villain_action")
    if is_placeholder(villain):
        out.append(_issue(
            ch, "CH-09", "high",
            f"第{n}章 villain_action 无效",
            field="extra.villain_action",
            suggestion="补反派本卷独立行动",
        ))

    if not ch.involved_character_ids:
        out.append(_issue(
            ch, "CH-10", "medium",
            f"第{n}章无出场人物",
            field="involved_character_ids",
            suggestion="至少关联一名已知角色",
        ))

    if not ch.storyline_ids:
        out.append(_issue(
            ch, "CH-11", "medium",
            f"第{n}章未挂故事线",
            field="storyline_ids",
            suggestion="至少推进一条故事线",
        ))

    pacing = (ch.pacing or "normal").lower()
    if pacing not in {"fast", "normal", "slow", "climax"}:
        out.append(_issue(
            ch, "CH-12", "medium",
            f"第{n}章 pacing 非法：{ch.pacing!r}",
            field="pacing",
            suggestion="使用 fast/normal/slow/climax",
        ))

    phase = ch.phase or "rising"
    has_slap = bool((ch.extra or {}).get("has_face_slap"))
    has_beat = bool((ch.extra or {}).get("has_emotional_beat"))
    if ch.expected_words is not None:
        target = chapter_word_budget_for_phase(phase, pacing, has_slap, has_beat)
        if ch.expected_words < target - 400 or ch.expected_words > target + 600:
            out.append(_issue(
                ch, "CH-15", "medium",
                f"第{n}章 expected_words={ch.expected_words} 偏离阶段预算 {target}",
                field="expected_words",
                suggestion="按 phase/pacing 调整字数预期",
            ))

    milestone = (ch.power_milestone or "").strip()
    if milestone and len(milestone) < 12 and any(k in milestone for k in VAGUE_POWER_RE):
        out.append(_issue(
            ch, "CH-18", "medium",
            f"第{n}章 power_milestone 过泛",
            field="power_milestone",
            suggestion="写清境界名/技能名",
        ))

    return out
