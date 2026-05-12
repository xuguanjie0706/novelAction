"""硬规则与 embedding 语义去重共用的严重度→分数映射。"""
from __future__ import annotations

_HARD_RULE_SEVERITY_TO_SCORE: dict[str, int] = {
    "critical": 55,
    "high": 70,
    "medium": 80,
    "low": 90,
}

