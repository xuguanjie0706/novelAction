"""realm_effective 单元测试。"""

from app.services.bootstrap.realm_effective import effective_realm_score, parse_sub_stage_index


def test_sub_stage_ordering():
    assert parse_sub_stage_index("破虚境初期") == 0
    assert parse_sub_stage_index("破虚境圆满") == 3
    assert effective_realm_score(5, "破虚境初期") < effective_realm_score(5, "破虚境圆满")
    assert effective_realm_score(5, "破虚境") == effective_realm_score(5, "破虚境")


def test_equal_major_without_sub_is_equal_score():
    assert effective_realm_score(5, "破虚境") == effective_realm_score(5, "破虚境")
