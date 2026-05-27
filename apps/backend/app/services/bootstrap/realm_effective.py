"""大境 + 小境有效战力分：同大境内允许「初期→圆满」递进。"""
from __future__ import annotations

# 小境标签 → 序（越大越强）
_SUB_STAGE_INDEX: dict[str, int] = {
    "前期": 0,
    "初期": 0,
    "一重": 0,
    "二层": 0,
    "中期": 1,
    "二重": 1,
    "后期": 2,
    "三重": 2,
    "巅峰": 3,
    "圆满": 3,
    "四重": 3,
    "大圆满": 4,
    "五重": 4,
}

_DEFAULT_SUB_LABELS = ("初期", "中期", "后期", "圆满")


def parse_sub_stage_index(realm_label: str | None) -> int | None:
    """从「破虚境中期」等字符串解析小境序；无标注返回 None。"""
    if not realm_label or not str(realm_label).strip():
        return None
    text = str(realm_label).strip()
    for label, idx in sorted(_SUB_STAGE_INDEX.items(), key=lambda x: -len(x[0])):
        if label in text:
            return idx
    return None


def effective_realm_score(major_rank: int, realm_label: str = "") -> float:
    """合成可比分数：大境 rank + 小境小数偏移（同大境可区分强弱）。"""
    if major_rank < 0:
        return -1.0
    sub = parse_sub_stage_index(realm_label)
    if sub is None:
        return float(major_rank)
    return major_rank + (sub + 1) / 10.0


def suggest_higher_sub_stage(major_realm_name: str, current_label: str = "") -> str:
    """同大境时建议下一档小境名（用于 lint suggestion）。"""
    base = (major_realm_name or "").strip()
    if not base:
        return current_label
    cur = parse_sub_stage_index(current_label)
    if cur is None:
        return f"{base}{_DEFAULT_SUB_LABELS[1]}"
    nxt = min(cur + 1, len(_DEFAULT_SUB_LABELS) - 1)
    return f"{base}{_DEFAULT_SUB_LABELS[nxt]}"


def format_realm_with_sub(major_realm_name: str, sub_index: int) -> str:
    """大境 canonical 名 + 小境后缀。"""
    base = (major_realm_name or "").strip()
    if not base:
        return ""
    idx = max(0, min(sub_index, len(_DEFAULT_SUB_LABELS) - 1))
    return f"{base}{_DEFAULT_SUB_LABELS[idx]}"
