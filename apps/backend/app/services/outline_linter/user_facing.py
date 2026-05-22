"""章纲 linter 阻断时面向用户的说明文案（Bootstrap SSE / 步骤暂停 / 大纲展开）。"""

from __future__ import annotations

from typing import Any

from app.services.outline_linter.gate import BLOCKING_RULE_IDS

# 规则编号 → 作者可读简称（前端展示与门控摘要共用）
RULE_LABELS: dict[str, str] = {
    "CH-01": "章纲·主角欲望过短",
    "CH-02": "章纲·障碍过短",
    "CH-03": "章纲·关键选择过短",
    "CH-04": "章纲·选择代价为空",
    "CH-05": "章纲·开篇钩子过短",
    "CH-06": "章纲·章末钩子过短",
    "CH-07": "章纲·章末钩子空泛",
    "CH-08": "章纲·核心事件为空",
    "CH-09": "章纲·反派行动无效",
    "CH-10": "章纲·无出场人物",
    "CH-11": "章纲·未挂故事线",
    "CH-12": "章纲·节奏标记非法",
    "CH-15": "章纲·字数预期偏离",
    "CH-18": "章纲·实力里程碑过泛",
    "SEQ-01": "章间衔接·代价未承接",
    "SEQ-02": "章间衔接·故事线独占",
    "SEQ-03": "章间衔接·至暗期过快",
    "SEQ-04": "章间衔接·至暗期情感不足",
    "SEQ-05": "章间衔接·梗概雷同",
    "SEQ-07": "章间衔接·分批断档",
    "VL-01": "卷纲·章数与配额不符",
    "VL-02": "卷纲·章节排序断裂",
    "VL-03": "卷纲·全卷无爽点章",
    "VL-04": "卷纲·打脸节奏",
    "VL-05": "卷纲·长线伏笔不足",
    "VL-06": "卷纲·无伏笔回收",
    "VL-07": "卷纲·故事线单一",
    "VL-09": "卷间衔接·开篇未接悬念",
    "VL-10": "卷间衔接·首章无后遗症",
    "RP-01": "读者承诺·超窗未兑现",
    "RP-02": "读者承诺·窗口未填兑现",
    "RP-03": "读者承诺·关键词不符",
    "OC-01": "开局·第1章钩子",
    "OC-02": "开局·前3章无爽点",
    "OC-03": "开局·第5章未埋长线",
    "OC-04": "开局·第10章钩子偏弱",
    "CM-01": "核心谜题·埋设章缺失",
    "CM-02": "核心谜题·加热章缺失",
    "CM-03": "核心谜题·揭晓过早",
    "CM-04": "核心谜题·揭晓章未收束",
    "CM-05": "核心谜题·缺身份之谜",
    "CM-06": "核心谜题·揭晓过密",
    "GEN-01": "生成·章数与要求不符",
}

RULE_HINTS: dict[str, str] = {
    "CH-04": "本章「选择代价」为空或仅占位，下一章无法承接",
    "CH-08": "本章「核心事件」为空",
    "VL-01": "生成章数与卷配额不一致",
    "SEQ-07": "分两批生成时，第31章开篇须硬承接第30章代价",
    "SEQ-01": "本章开篇/梗概须体现上一章「选择代价」的后果",
    "RP-01": "高优先级读者承诺已超过兑现窗口",
    "CM-03": "核心谜题揭晓章距埋设章不足10章",
    "GEN-01": "AI 返回章数与批次要求不一致",
    "OC-03": "开局第5章须埋下跨卷长线伏笔",
}

SEVERITY_LABELS: dict[str, str] = {
    "critical": "严重",
    "high": "较高",
    "medium": "中等",
    "low": "轻微",
}

STATUS_LABELS: dict[str, str] = {
    "failed": "未通过",
    "warn": "有警告",
    "ok": "通过",
}


def rule_label(rule_id: str) -> str:
    return RULE_LABELS.get(rule_id, rule_id)


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
    """单行人类可读问题描述（面向作者，不含英文字段名）。"""
    rid = str(issue.get("rule_id") or "?")
    label = rule_label(rid)
    ch = issue.get("chapter_number_in_volume")
    msg = str(issue.get("message") or RULE_HINTS.get(rid, "质量检查未通过"))
    sug = str(issue.get("suggestion") or "").strip()

    if isinstance(ch, int) and msg.startswith(f"第{ch}章"):
        line = f"{label}：{msg}"
    elif isinstance(ch, int):
        line = f"第{ch}章 · {label}：{msg}"
    else:
        line = f"{label}：{msg}"

    if sug:
        line += f"（建议：{sug}）"
    return line


def build_linter_block_payload(
    report: dict[str, Any],
    *,
    chapter_count: int = 0,
) -> dict[str, Any]:
    """生成阻断时的 SSE / 暂停消息字段。"""
    issues_raw = report.get("issues") or []
    issues: list[dict[str, Any]] = [
        i for i in issues_raw if isinstance(i, dict)
    ] if isinstance(issues_raw, list) else []

    critical = int(report.get("critical_count") or 0)
    high = int(report.get("high_count") or 0)
    issue_count = int(report.get("issue_count") or len(issues))
    status = str(report.get("status") or "failed")
    status_cn = STATUS_LABELS.get(status, status)

    blocking_ids = sorted({
        str(i.get("rule_id"))
        for i in issues
        if str(i.get("rule_id")) in BLOCKING_RULE_IDS
    })
    top = select_top_issues(issues, limit=8)

    hint_lines = [
        RULE_HINTS.get(rid) or rule_label(rid)
        for rid in blocking_ids
    ]
    detail_lines = [format_issue_line(i) for i in top]

    if chapter_count > 0:
        persist_note = (
            f"已暂存 {chapter_count} 章草稿（卷已标为待修复），"
            "可在大纲页逐章修改后点「重新检测」。"
        )
    else:
        persist_note = "章纲未写入数据库。"

    sev_parts: list[str] = []
    if critical:
        sev_parts.append(f"严重 {critical}")
    if high:
        sev_parts.append(f"较高 {high}")
    sev_tail = " / ".join(sev_parts) if sev_parts else "无严重项"

    message_parts = [
        (
            f"章纲质量门控{status_cn}（{sev_tail}，共 {issue_count} 项）。{persist_note}"
        ),
    ]
    if blocking_ids:
        message_parts.append("须优先处理：" + "；".join(hint_lines))
    if detail_lines:
        message_parts.append("主要问题：\n" + "\n".join(f"· {ln}" for ln in detail_lines))
    message_parts.append(
        "下一步：大纲 → 选中该卷 →「章纲检测」查看完整列表；"
        "修复后点「重新生成此步」，或使用「按 linter 建议发起卷级修复」。"
    )

    preview = (
        f"{'草稿已暂存' if chapter_count > 0 else '未落库'} · 质检{status_cn}"
        f"（{sev_tail}）"
    )
    if blocking_ids:
        preview += " · 阻断：" + "、".join(rule_label(rid) for rid in blocking_ids)

    return {
        "linter_message": "\n".join(message_parts),
        "linter_blocking_rules": blocking_ids,
        "linter_issues_top": top,
        "preview": preview,
        "linter_draft_saved": chapter_count > 0,
    }
