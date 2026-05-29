"""生成期回灌 prompt 块（支柱一：在源头减少问题）。

职责：把历史高频问题转写为「本卷生成时必须规避」的约束，并对最常见的低质字段
（choice_cost / end_hook / villain_action）附正反 few-shot，注入章纲生成上下文。
约束：纯字符串构造，无 DB（调用方传入 top_frequent_issues 结果）；保持 <150 行。
"""

from __future__ import annotations

from typing import Any

# 维度 → 人类可读约束标题
_DIMENSION_LABEL: dict[str, str] = {
    "chapter_craft": "单章工艺（钩子/核心事件/选择代价）",
    "continuity": "章际连贯（代价承接、避免重复）",
    "volume_beat": "卷级节拍（燃点与高潮呼应）",
    "reader_promise": "读者承诺兑现",
    "core_mystery": "核心谜题推进",
    "opening_contract": "开局追读承诺",
    "generation": "生成结构完整性",
    "other": "其它",
}

# 高频字段的正反样例（few-shot）：让模型「照着写对的，避开写错的」
_FEW_SHOT: dict[str, dict[str, str]] = {
    "extra.choice_cost": {
        "title": "选择代价（choice_cost）",
        "bad": "主角做出了选择，付出了代价。（空泛，未指明放弃了什么）",
        "good": "为救妹妹，主角交出唯一能压制心魔的「锁灵玉」，自此夜不能寐、修为停滞三月。",
    },
    "end_hook": {
        "title": "章末钩子（end_hook）",
        "bad": "他决定继续前进，看看接下来会发生什么。（无悬念、无新信息）",
        "good": "他推开石门，火把照亮的不是宝库，而是一具穿着自己衣服的尸体。",
    },
    "extra.villain_action": {
        "title": "反派行动（villain_action）",
        "bad": "反派在暗中谋划着什么。（无具体动作、不可证伪）",
        "good": "黑袍长老借赈灾之名调走城卫，连夜把三名证人灭口，并嫁祸给主角师门。",
    },
}


def build_issue_feedback_block(top_issues: list[dict[str, Any]]) -> str:
    """由高频问题列表构造回灌约束块。无问题则返回空串。"""
    if not top_issues:
        return ""

    lines: list[str] = [
        "【历史高频问题 · 本卷生成必须规避】",
        "以下是本项目此前章纲质检中反复出现的问题，按出现频次排序。"
        "请在生成本卷章纲时主动规避——这是减少返工的关键：",
    ]
    seen_fields: list[str] = []
    for idx, item in enumerate(top_issues, 1):
        dim = _DIMENSION_LABEL.get(item.get("dimension", "other"), item.get("dimension", ""))
        rule = item.get("rule_id", "")
        cnt = item.get("count", 0)
        sug = (item.get("suggestion") or "").strip()
        tail = f" 修复方向：{sug}" if sug else ""
        lines.append(f"{idx}. [{rule} · {dim}] 累计命中 {cnt} 次。{tail}")
        field = item.get("field") or ""
        if field in _FEW_SHOT and field not in seen_fields:
            seen_fields.append(field)

    fewshot_block = _build_fewshot(seen_fields)
    if fewshot_block:
        lines.append("")
        lines.append(fewshot_block)
    return "\n".join(lines)


def _build_fewshot(fields: list[str]) -> str:
    """对命中的高频字段拼接正反样例。"""
    if not fields:
        return ""
    parts: list[str] = ["【高频字段正反示范】"]
    for f in fields:
        spec = _FEW_SHOT.get(f)
        if not spec:
            continue
        parts.append(
            f"· {spec['title']}\n"
            f"  ✗ 反例：{spec['bad']}\n"
            f"  ✓ 正例：{spec['good']}"
        )
    return "\n".join(parts) if len(parts) > 1 else ""
