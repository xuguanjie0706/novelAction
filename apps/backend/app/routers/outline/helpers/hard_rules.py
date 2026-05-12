"""大纲硬规则聚合：镜像重复、术语、战力、生死、主题、伏笔等。"""
from __future__ import annotations

from app.routers.outline.helpers.detectors import (
    _detect_outline_character_death_continuity,
    _detect_outline_foreshadow_issues,
    _detect_outline_power_curve_issues,
    _detect_outline_theme_alignment_issues,
)
from app.routers.outline.helpers.duplicate_sig import _chapter_duplicate_signature
from app.routers.outline.helpers.realm_timeline import (
    _collect_protagonist_anchor_names,
    _detect_outline_terminology_issues,
)
from app.routers.outline.helpers.severity import _HARD_RULE_SEVERITY_TO_SCORE

def _detect_outline_hard_rule_issues(
    chapters: list[dict],
    *,
    power_systems=None,
    genre: str = "",
    scope: str = "volume",
    characters=None,
    theme_statement: str = "",
    premise: str = "",
    foreshadows=None,
) -> dict:
    """
    Deterministic outline checks for failures that should not depend on LLM judgment.
    Sub-checks:
      1. Exact mirrored chapter endings (duplicate_event / critical) — always on.
      2. Power-system terminology drift (continuity / critical) — when power_systems provided.
      3. Realm regression without trigger + end-of-book pacing collapse
         (continuity / pacing / high) — when power_systems provided.
      4. Character death without revival mechanism (continuity / critical)
         — when characters provided.
      5. Theme alignment (theme_alignment / medium) — when theme_statement contains
         self-determination keywords (我命由我 / 凡人逆袭 / 草根崛起 ...).
      6. Foreshadow ledger overdue / abandoned (pacing or continuity / medium-high)
         — when foreshadows provided.

    Backward compatibility: when all extra context kwargs are absent, only the
    duplicate_event check runs and the original score (55 on fail, 100 on pass) is
    preserved.
    """
    issues: list[dict] = []
    must_fix: set[int] = set()
    protagonist_names = _collect_protagonist_anchor_names(characters)

    # Sub-check 1: exact mirrored core_event/character_change/end_hook (existing logic)
    signatures: dict[tuple[str, str, str], list[int]] = {}
    for chapter in chapters:
        signature = _chapter_duplicate_signature(chapter)
        number = chapter.get("number")
        if signature is None or not isinstance(number, int):
            continue
        signatures = {
            **signatures,
            signature: [*signatures.get(signature, []), number],
        }
    for numbers in signatures.values():
        if len(numbers) < 2:
            continue
        ordered_numbers = sorted(numbers)
        must_fix = {*must_fix, *ordered_numbers}
        issues.append({
            "severity": "critical",
            "type": "duplicate_event",
            "chapter_numbers": ordered_numbers,
            "description": (
                f"第{'、'.join(str(n) for n in ordered_numbers)}章的核心事件、人物变化、章末钩子完全一致，"
                "属于确定性镜像重复，会制造多个同质结局或循环节点。"
            ),
            "suggested_patch": {
                "chapter_number": ordered_numbers[-1],
                "field": "core_event",
                "replacement": "",
            },
        })

    # Sub-check 2: terminology hard whitelist/blacklist
    terminology_issues = _detect_outline_terminology_issues(
        chapters,
        power_systems=power_systems,
        genre=genre,
    )
    for issue in terminology_issues:
        for number in issue.get("chapter_numbers", []) or []:
            if isinstance(number, int):
                must_fix.add(number)
    issues.extend(terminology_issues)

    # Sub-check 3: realm regression + end-of-book pacing
    power_curve_issues = _detect_outline_power_curve_issues(
        chapters,
        power_systems=power_systems,
        scope=scope,
        protagonist_names=protagonist_names or None,
    )
    for issue in power_curve_issues:
        for number in issue.get("chapter_numbers", []) or []:
            if isinstance(number, int):
                must_fix.add(number)
    issues.extend(power_curve_issues)

    # Sub-check 4: character death continuity
    death_issues = _detect_outline_character_death_continuity(
        chapters,
        characters=characters,
    )
    for issue in death_issues:
        for number in issue.get("chapter_numbers", []) or []:
            if isinstance(number, int):
                must_fix.add(number)
    issues.extend(death_issues)

    # Sub-check 5: theme alignment
    theme_protagonist_names = [
        getattr(char, "name", None) for char in (characters or [])
        if getattr(char, "role", None) == "protagonist" and getattr(char, "name", None)
    ]
    theme_issues = _detect_outline_theme_alignment_issues(
        chapters,
        theme_statement=theme_statement,
        premise=premise,
        protagonist_names=theme_protagonist_names,
    )
    for issue in theme_issues:
        for number in issue.get("chapter_numbers", []) or []:
            if isinstance(number, int):
                must_fix.add(number)
    issues.extend(theme_issues)

    # Sub-check 6: foreshadow ledger
    foreshadow_issues = _detect_outline_foreshadow_issues(
        chapters,
        foreshadows=foreshadows,
    )
    for issue in foreshadow_issues:
        for number in issue.get("chapter_numbers", []) or []:
            if isinstance(number, int):
                must_fix.add(number)
    issues.extend(foreshadow_issues)

    if not issues:
        return {
            "overall_score": 100,
            "status": "pass",
            "summary": "硬规则未发现确定性结构问题。",
            "issues": [],
            "must_fix_chapter_numbers": [],
        }

    score = min(
        _HARD_RULE_SEVERITY_TO_SCORE.get(issue.get("severity", ""), 80)
        for issue in issues
    )

    return {
        "overall_score": score,
        "status": "fail",
        "summary": f"硬规则发现 {len(issues)} 个确定性结构问题。",
        "issues": issues,
        "must_fix_chapter_numbers": sorted(must_fix),
    }
