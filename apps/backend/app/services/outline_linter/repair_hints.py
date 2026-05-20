"""将 linter issues 转为修复工作流种子（供 AI repair 或人工）。"""

from __future__ import annotations

from typing import Any

from app.services.outline_linter.schemas import LinterIssue, LinterReport

# linter field → outline_repair 常用字段名
_FIELD_TO_REPAIR: dict[str, str] = {
    "extra.choice_cost": "choice_cost",
    "extra.protagonist_want": "protagonist_want",
    "extra.protagonist_obstacle": "protagonist_obstacle",
    "extra.protagonist_choice": "protagonist_choice",
    "extra.villain_action": "villain_action",
    "extra.end_hook": "end_hook",
    "hook": "opening_hook",
    "summary": "core_event",
    "extra.foreshadow": "foreshadow",
    "extra.promise_fulfilled": "promise_fulfilled",
}


def build_repair_seed(report: LinterReport) -> dict[str, Any]:
    """从 linter 报告生成修复种子，可传入 outline repair workflow。"""
    must_fix: set[int] = set()
    by_chapter: dict[int, list[dict[str, str]]] = {}

    for issue in report.issues:
        if issue.severity not in ("critical", "high"):
            continue
        ch = issue.chapter_number_in_volume
        if ch is not None:
            must_fix.add(ch)
            repair_field = _FIELD_TO_REPAIR.get(issue.field, "")
            by_chapter.setdefault(ch, []).append({
                "rule_id": issue.rule_id,
                "message": issue.message,
                "field": repair_field or issue.field,
                "suggestion": issue.suggestion,
            })

    return {
        "must_fix_chapter_numbers": sorted(must_fix),
        "issues_by_chapter": {
            str(k): v for k, v in sorted(by_chapter.items())
        },
        "critical_count": report.critical_count,
        "high_count": report.high_count,
        "summary": (
            f"linter 检出 {len(report.issues)} 项；"
            f"建议优先修复 {len(must_fix)} 章（critical/high）"
        ),
    }
