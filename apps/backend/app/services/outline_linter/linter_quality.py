"""Linter 报告 → 大纲质检/修复工作流可消费格式。"""

from __future__ import annotations

from typing import Any

from app.services.outline_linter.repair_hints import build_repair_seed
from app.services.outline_linter.schemas import LinterReport

_SEVERITY_TO_SCORE = {
    "critical": 40,
    "high": 55,
    "medium": 72,
    "low": 85,
}


def linter_report_to_quality_report(report: LinterReport) -> dict[str, Any]:
    """将 LinterReport 转为与 outline QC 兼容的 quality_report 结构。"""
    must_fix: set[int] = set()
    issues: list[dict] = []
    for item in report.issues:
        ch = item.chapter_number_in_volume
        if ch is not None and item.severity in ("critical", "high"):
            must_fix.add(ch)
        entry: dict[str, Any] = {
            "severity": item.severity,
            "type": f"linter_{item.rule_id}",
            "rule_id": item.rule_id,
            "description": item.message,
            "suggestion": item.suggestion,
            "auto_detected": True,
            "source": "outline_linter",
        }
        if ch is not None:
            entry["chapter_numbers"] = [ch]
        issues.append(entry)

    score = 100
    if issues:
        score = min(_SEVERITY_TO_SCORE.get(i["severity"], 80) for i in issues)

    return {
        "overall_score": score,
        "status": "fail" if report.status != "ok" else "pass",
        "summary": (
            f"章纲 linter（v{report.linter_version}）检出 {len(issues)} 项，"
            f"状态={report.status}"
        ),
        "issues": issues,
        "must_fix_chapter_numbers": sorted(must_fix),
        "source": "outline_linter",
    }


def merge_linter_into_quality_report(
    base_report: dict | None,
    linter_report: LinterReport | dict,
) -> dict[str, Any]:
    """合并已有质检报告与 linter 报告（linter 问题置顶）。"""
    if isinstance(linter_report, dict):
        linter_q = dict(linter_report)
        if "issues" not in linter_q and "must_fix_chapter_numbers" not in linter_q:
            linter_q = linter_report_to_quality_report(
                _report_from_dict(linter_report)
            )
    else:
        linter_q = linter_report_to_quality_report(linter_report)

    base = dict(base_report or {})
    if not base:
        return linter_q

    merged_issues = list(linter_q.get("issues") or []) + list(base.get("issues") or [])
    must_fix = sorted({
        *(
            n
            for n in (linter_q.get("must_fix_chapter_numbers") or [])
            if isinstance(n, int)
        ),
        *(
            n
            for n in (base.get("must_fix_chapter_numbers") or [])
            if isinstance(n, int)
        ),
    })
    score = min(
        int(linter_q.get("overall_score", 100)),
        int(base.get("overall_score", 100)),
    )
    return {
        **base,
        "overall_score": score,
        "status": "fail" if score < 70 or must_fix else base.get("status", "warning"),
        "summary": f"{linter_q.get('summary', '')}；{base.get('summary', '')}".strip("；"),
        "issues": merged_issues,
        "must_fix_chapter_numbers": must_fix,
        "linter_merged": True,
        "repair_seed": build_repair_seed(
            linter_report
            if isinstance(linter_report, LinterReport)
            else _report_from_dict(linter_report if isinstance(linter_report, dict) else linter_q)
        ),
    }


def _report_from_dict(data: dict) -> LinterReport:
    from app.services.outline_linter.schemas import LinterIssue

    report = LinterReport(
        linter_version=data.get("linter_version", "1.2.0"),
        status=data.get("status", "warn"),
    )
    for raw in data.get("issues") or []:
        if not isinstance(raw, dict):
            continue
        report.issues.append(LinterIssue(
            rule_id=str(raw.get("rule_id", "")),
            severity=str(raw.get("severity", "medium")),
            scope=str(raw.get("scope", "chapter")),
            message=str(raw.get("message", "")),
            suggestion=str(raw.get("suggestion", "")),
            field=str(raw.get("field", "")),
            chapter_number_in_volume=raw.get("chapter_number_in_volume"),
            node_id=raw.get("node_id"),
        ))
    report.finalize_status()
    return report


def build_linter_repair_context_block(
    volume_extra: dict | None,
    repair_seed: dict | None = None,
) -> str:
    """生成注入 outline_repair_plan 的 linter 约束块。"""
    extra = volume_extra or {}
    seed = repair_seed or {}
    issues = extra.get("linter_issues") or []
    if not issues and not seed:
        return ""

    lines = [
        "【章纲 linter 硬性欠债（修复补丁必须逐条消化，不得忽略）】",
        f"卷级状态：{extra.get('linter_status', 'unknown')}",
    ]
    if seed.get("must_fix_chapter_numbers"):
        lines.append(
            "优先修复章节号："
            + "、".join(str(n) for n in seed["must_fix_chapter_numbers"])
        )
    for item in issues[:15]:
        if not isinstance(item, dict):
            continue
        if item.get("severity") not in ("critical", "high"):
            continue
        ch = item.get("chapter_number_in_volume")
        prefix = f"第{ch}章" if ch else "卷级"
        lines.append(
            f"  - [{item.get('rule_id', '?')}] {prefix}：{item.get('message', '')}"
        )
        if item.get("suggestion"):
            lines.append(f"    建议：{item['suggestion']}")
    lines.append(
        "修复时保持立项定位与故事线；linter 标记的 choice_cost / end_hook / foreshadow 字段优先补齐。"
    )
    return "\n".join(lines)
