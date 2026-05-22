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
            f"第{n}章「主角欲望」过短或为空",
            field="extra.protagonist_want",
            suggestion="补写主角本章的主动目标（要/想/必须/决定…）",
        ))

    obstacle = ch.ex_str("protagonist_obstacle")
    if len(obstacle) < MIN_TEXT_LEN:
        out.append(_issue(
            ch, "CH-02", "high",
            f"第{n}章「具体障碍」过短或为空",
            field="extra.protagonist_obstacle",
            suggestion="补写阻碍主角达成目标的具体阻力",
        ))

    choice = ch.ex_str("protagonist_choice")
    if len(choice) < MIN_TEXT_LEN:
        out.append(_issue(
            ch, "CH-03", "high",
            f"第{n}章「关键选择」过短或为空",
            field="extra.protagonist_choice",
            suggestion="补写暴露性格、推动剧情的关键抉择",
        ))

    cost = ch.ex_str("choice_cost")
    if is_placeholder(cost):
        out.append(_issue(
            ch, "CH-04", "critical",
            f"第{n}章「选择代价」为空或仅占位",
            field="extra.choice_cost",
            suggestion="补写本章选择带来的损失/风险，供下一章开篇承接",
            auto_fixable=True,
        ))

    hook = (ch.hook or "").strip()
    if len(hook) < MIN_HOOK_LEN:
        out.append(_issue(
            ch, "CH-05", "high",
            f"第{n}章「开篇钩子」过短或为空",
            field="hook",
            suggestion="补写开篇抓人手段（前几百字须有画面或冲突）",
        ))

    end_hook = ch.end_hook_text()
    if len(end_hook) < MIN_END_HOOK_LEN:
        out.append(_issue(
            ch, "CH-06", "high",
            f"第{n}章「章末钩子」过短或为空",
            field="extra.end_hook",
            suggestion="补写具体章末悬念或反转画面",
        ))
    elif is_vague_end_hook(end_hook):
        out.append(_issue(
            ch, "CH-07", "medium",
            f"第{n}章「章末钩子」过于空泛",
            field="extra.end_hook",
            suggestion="避免「悬念丛生」等套话，改具体画面或信息差",
        ))

    summary = (ch.summary or "").strip()
    if not summary:
        out.append(_issue(
            ch, "CH-08", "critical",
            f"第{n}章「核心事件」为空",
            field="summary",
            suggestion="补写本章发生的核心剧情事件",
        ))

    villain = ch.ex_str("villain_action")
    if is_placeholder(villain):
        out.append(_issue(
            ch, "CH-09", "high",
            f"第{n}章「反派行动」无效或占位",
            field="extra.villain_action",
            suggestion="补写反派/对立面在本章的独立行动",
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
            f"第{n}章「节奏」标记无效：{ch.pacing!r}",
            field="pacing",
            suggestion="请使用：快 / 正常 / 慢 / 高潮（对应 fast/normal/slow/climax）",
        ))

    phase = ch.phase or "rising"
    has_slap = bool((ch.extra or {}).get("has_face_slap"))
    has_beat = bool((ch.extra or {}).get("has_emotional_beat"))
    if ch.expected_words is not None:
        target = chapter_word_budget_for_phase(phase, pacing, has_slap, has_beat)
        # 仅提示偏短：高潮/打脸章写长一些不视为问题
        if ch.expected_words < target - 400:
            out.append(_issue(
                ch, "CH-15", "medium",
                f"第{n}章预期字数 {ch.expected_words} 低于本阶段建议 {target} 字"
                f"（偏短 {target - ch.expected_words} 字）",
                field="expected_words",
                suggestion="按卷阶段与节奏上调本章字数预期，或确认本章确实宜短写",
            ))

    milestone = (ch.power_milestone or "").strip()
    if milestone and len(milestone) < 12 and any(k in milestone for k in VAGUE_POWER_RE):
        out.append(_issue(
            ch, "CH-18", "medium",
            f"第{n}章「实力里程碑」表述过泛",
            field="power_milestone",
            suggestion="写清具体境界名、技能名或战力变化",
        ))

    return out
