"""consistency_fix 路由辅助逻辑（无 LLM）。"""

from app.routers.consistency_fix import _is_manual_only_issue


def test_manual_only_storyline_gap():
    assert _is_manual_only_issue({"type": "storyline_gap", "suggestion": "增加御火道途层级"})


def test_realm_mismatch_with_power_system_wording_not_manual():
    """描述含「境界体系」但建议改人物境界 → 应允许远程/规则修复。"""
    assert not _is_manual_only_issue({
        "type": "realm_mismatch",
        "description": "韩厉境界标注为战卒，与主轴境界体系名称不一致",
        "suggestion": "参照主轴统一标注为灵徒境",
    })
    assert not _is_manual_only_issue({
        "type": "realm_mismatch",
        "description": "莫沧作为最终BOSS，未达到境界体系上限虚神境",
        "suggestion": "将莫沧终局境界设为虚神境",
    })


def test_path_level_expand_is_manual():
    assert _is_manual_only_issue({
        "type": "storyline_gap",
        "suggestion": "增加御火道途层级或扩充设定",
    })
