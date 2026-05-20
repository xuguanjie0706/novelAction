"""Bootstrap / SSE 用 linter 摘要字段。"""

from __future__ import annotations

from typing import Any


def build_vol1_chapters_sse_payload(
    plans: list[Any],
    ctx: dict[str, Any],
    *,
    volume_extra: dict | None = None,
) -> dict[str, Any]:
    """生成 vol1_chapters 的 step_done 附加字段（含 linter_blocked 说明）。

    Returns:
        count, preview, linter_blocked, linter_status, linter_issue_count,
        linter_critical_count, linter_high_count, linter_message（可选）
    """
    blocked = bool(ctx.get("linter_blocked"))
    report = ctx.get("linter_last_report") if isinstance(ctx.get("linter_last_report"), dict) else {}
    extra = volume_extra or {}

    if blocked:
        issue_count = int(report.get("issue_count") or len(report.get("issues") or []))
        critical = int(report.get("critical_count") or 0)
        high = int(report.get("high_count") or 0)
        status = str(report.get("status") or extra.get("linter_status") or "failed")
        return {
            "count": 0,
            "preview": (
                f"章纲未落库：linter {status}（critical {critical} / high {high} / 共 {issue_count} 项）"
            ),
            "linter_blocked": True,
            "linter_status": status,
            "linter_issue_count": issue_count,
            "linter_critical_count": critical,
            "linter_high_count": high,
            "linter_message": (
                "第一卷章纲存在 critical 问题，已阻断落库。"
                "请进入项目 → 大纲 → 第一卷「章纲检测」查看并修复后重新生成。"
            ),
        }

    if plans:
        summary = extra.get("linter_summary") or {}
        status = str(extra.get("linter_status") or "ok")
        issue_count = int(summary.get("issue_count") or 0)
        preview = f"第一卷共 {len(plans)} 章蓝图"
        if status != "ok" and issue_count > 0:
            preview += f" · linter {status}（{issue_count} 项待处理）"
        return {
            "count": len(plans),
            "preview": preview,
            "linter_blocked": False,
            "linter_status": status,
            "linter_issue_count": issue_count,
            "linter_critical_count": int(summary.get("critical_count") or 0),
            "linter_high_count": int(summary.get("high_count") or 0),
        }

    return {
        "count": 0,
        "preview": "（跳过）",
        "linter_blocked": False,
        "linter_status": "unknown",
        "linter_issue_count": 0,
        "linter_critical_count": 0,
        "linter_high_count": 0,
    }
