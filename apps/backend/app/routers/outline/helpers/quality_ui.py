"""质检报告合并、标签文案与 SSE 进度行。"""
from __future__ import annotations

import json

def _merge_outline_quality_reports(ai_report: dict, hard_report: dict) -> dict:
    hard_issues = hard_report.get("issues") if isinstance(hard_report, dict) else []
    if not hard_issues:
        return ai_report

    ai_issues = ai_report.get("issues") if isinstance(ai_report, dict) else []
    ai_must_fix = ai_report.get("must_fix_chapter_numbers") if isinstance(ai_report, dict) else []
    hard_must_fix = hard_report.get("must_fix_chapter_numbers") or []
    merged_must_fix = sorted({
        *[n for n in ai_must_fix if isinstance(n, int)],
        *[n for n in hard_must_fix if isinstance(n, int)],
    })

    ai_score = ai_report.get("overall_score") if isinstance(ai_report, dict) else None
    hard_score = hard_report.get("overall_score", 55)
    score = min(ai_score if isinstance(ai_score, int) else 100, hard_score)
    ai_summary = ai_report.get("summary", "") if isinstance(ai_report, dict) else ""
    hard_summary = hard_report.get("summary", "")
    summary = "；".join(part for part in [hard_summary, ai_summary] if part)

    return {
        **(ai_report if isinstance(ai_report, dict) else {}),
        "overall_score": score,
        "status": "fail",
        "summary": summary,
        "issues": [*hard_issues, *(ai_issues if isinstance(ai_issues, list) else [])],
        "must_fix_chapter_numbers": merged_must_fix,
    }


def _format_outline_quality_label(node_title: str, report: dict, scope: str) -> str:
    scope_name = "全书" if scope == "book" else "卷内"
    if not isinstance(report, dict) or report.get("error"):
        return f"《{node_title}》{scope_name}质检失败：{report.get('error', '未知错误') if isinstance(report, dict) else '未知错误'}"
    score = report.get("overall_score", "-")
    status = report.get("status", "-")
    must_fix = report.get("must_fix_chapter_numbers") or []
    suffix = f"，必修章节：{'、'.join(str(num) for num in must_fix)}" if must_fix else ""
    return f"《{node_title}》{scope_name}质检完成：{score}分 / {status}{suffix}"


def _sse_outline_quality_progress(
    *,
    step: int,
    total_steps: int,
    label: str,
    scope: str,
    progress_key_suffix: str,
    report: dict | None = None,
    done: bool = True,
    error: bool = False,
) -> str:
    """SSE 进度行：携带结构化大纲质检结果供前端展开；progress_key 避免与同日 step 的其他进度行合并。"""
    payload: dict = {
        "event": "progress",
        "step": step,
        "total": total_steps,
        "label": label,
        "done": done,
        "error": error,
        "progress_key": f"{step}-outline-quality-{scope}-{progress_key_suffix}",
        "outline_quality_scope": scope,
    }
    if report is not None:
        payload["outline_quality_report"] = report
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

