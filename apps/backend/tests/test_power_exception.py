"""跨境破例预算（方向4）纯逻辑回归测试。"""
from types import SimpleNamespace

from app.services.ai.power_exception import (
    CROSS_TIER_THRESHOLD,
    build_power_exception_block,
    get_power_exception_budget,
)


def test_budget_empty_returns_zero_exception_rule():
    p = SimpleNamespace(extra={})
    assert get_power_exception_budget(p) == []
    block = build_power_exception_block(p)
    assert "未登记任何跨境破例" in block
    assert f"≥{CROSS_TIER_THRESHOLD}" in block


def test_budget_parsing_normalizes_fields():
    p = SimpleNamespace(extra={"power_exception_budget": [
        {"name": "至尊骨", "basis": "天生至尊骨", "max_span": 2, "budget": 3, "used": 1},
        {"no_name": "skip"},  # 无 name 跳过
    ]})
    budget = get_power_exception_budget(p)
    assert len(budget) == 1
    ex = budget[0]
    assert ex["name"] == "至尊骨" and ex["max_span"] == 2 and ex["budget"] == 3 and ex["used"] == 1


def test_block_lists_registered_with_remaining():
    p = SimpleNamespace(extra={"power_exception_budget": [
        {"name": "至尊骨", "basis": "可越阶", "max_span": 2, "budget": 3, "used": 3},
    ]})
    block = build_power_exception_block(p)
    assert "至尊骨" in block
    assert "剩余 0 次" in block  # 已用尽
    assert "未登记的设定不得用于越阶击杀" in block


def test_budget_defaults_used_zero():
    p = SimpleNamespace(extra={"power_exception_budget": [{"name": "血脉觉醒"}]})
    ex = get_power_exception_budget(p)[0]
    assert ex["used"] == 0 and ex["max_span"] == CROSS_TIER_THRESHOLD
