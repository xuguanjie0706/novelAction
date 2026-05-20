"""章纲 linter 阻断时面向用户的说明文案（Bootstrap SSE / 步骤暂停 / 大纲展开）。"""

from __future__ import annotations

from typing import Any

from app.services.outline_linter.gate import BLOCKING_RULE_IDS

RULE_HINTS: dict[str, str] = {
    "CH-04": "选择代价 choice_cost 为空或占位",
    "CH-08": "核心事件 core_event 为空",
    "VL-01": "章纲数量与卷配额不一致",
    "SEQ-07": "分批生成的第二批首章未承接上一批末章代价",
    "RP-01": "读者承诺在承诺窗口内未兑现",
    "CM-03": "核心谜题揭晓过早（距埋设不足 10 章）",
    "GEN-01": "AI 返回章数与批次要求不一致",
}


def _issue_sort_key(issue: dict[str, Any]) -> tuple:
    rid = str(issue.get("rule_id") or "")
    blocking = 0 if rid in BLOCKING_RULE_IDS else 1
    sev = str(issue.get("severity") or "")
    sev_rank = {"critical": 0, "high": 1, "medium": 2}.get(sev, 3)
    ch = issue.get("chapter_number_in_volume")
    ch_key = ch if isinstance(ch, int) else 9999
    return (blocking, sev_rank, ch_key)


def select_top_issues(issues: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    """优先返回阻断规则与 critical/high 问题。"""
    if not issues:
        return []
    ranked = sorted(
        [i for i in issues if isinstance(i, dict)],
        key=_issue_sort_key,
    )
    out: list[dict[str, Any]] = []
    for item in ranked:
        rid = str(item.get("rule_id") or "")
        sev = str(item.get("severity") or "")
        if rid in BLOCKING_RULE_IDS or sev in ("critical", "high"):
            out.append(item)
        if len(out) >= limit:
            break
    if len(out) < limit:
        for item in ranked:
            if item in out:
                continue
            out.append(item)
            if len(out) >= limit:
                break
    return out[:limit]


def format_issue_line(issue: dict[str, Any]) -> str:
    """单行人类可读问题描述。"""
    rid = str(issue.get("rule_id") or "?")
    ch = issue.get("chapter_number_in_volume")
    ch_part = f"第{ch}章 · " if isinstance(ch, int) else ""
    msg = str(issue.get("message") or RULE_HINTS.get(rid, "质量检查未通过"))
    sug = str(issue.get("suggestion") or "").strip()
    line = f"[{rid}] {ch_part}{msg}"
    if sug:
        line += f"（建议：{sug}）"
    return line


def build_linter_block_payload(
    report: dict[str, Any],
    *,
    chapter_count: int = 0,
) -> dict[str, Any]:
    """生成阻断时的 SSE / 暂停消息字段。

    Returns:
        linter_message, linter_blocking_rules, linter_issues_top, preview,
        linter_draft_saved
    """
    issues_raw = report.get("issues") or []
    issues: list[dict[str, Any]] = [
        i for i in issues_raw if isinstance(i, dict)
    ] if isinstance(issues_raw, list) else []

    critical = int(report.get("critical_count") or 0)
    high = int(report.get("high_count") or 0)
    issue_count = int(report.get("issue_count") or len(issues))
    status = str(report.get("status") or "failed")

    blocking_ids = sorted({
        str(i.get("rule_id"))
        for i in issues
        if str(i.get("rule_id")) in BLOCKING_RULE_IDS
    })
    top = select_top_issues(issues, limit=8)

    hint_lines = [f"{rid}（{RULE_HINTS.get(rid, '阻断规则')}）" for rid in blocking_ids]
    detail_lines = [format_issue_line(i) for i in top]

    if chapter_count > 0:
        persist_note = (
            f"已暂存 {chapter_count} 章草稿（卷已标 linter_blocked），"
            "可在大纲页逐章修改后点「重新检测」。"
        )
    else:
        persist_note = "章纲未写入数据库。"

    message_parts = [
        (
            f"章纲质量门控未通过：{status}，"
            f"critical {critical} / high {high} / 共 {issue_count} 项。{persist_note}"
        ),
    ]
    if blocking_ids:
        message_parts.append("阻断规则：" + "；".join(hint_lines))
    if detail_lines:
        message_parts.append("主要问题：\n" + "\n".join(f"· {ln}" for ln in detail_lines))
    message_parts.append(
        "下一步：大纲 → 选中该卷 →「章纲检测」查看完整列表；"
        "修复后在本流程「重新生成此步」，或使用「按 linter 建议发起卷级修复」。"
    )

    preview = (
        f"{'草稿已暂存' if chapter_count > 0 else '未落库'} · linter {status}"
        f"（critical {critical} / high {high}）"
    )
    if blocking_ids:
        preview += f" · 阻断：{', '.join(blocking_ids)}"

    return {
        "linter_message": "\n".join(message_parts),
        "linter_blocking_rules": blocking_ids,
        "linter_issues_top": top,
        "preview": preview,
        "linter_draft_saved": chapter_count > 0,
    }
