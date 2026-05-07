"""Regression tests for foreshadow code extraction from chapter-index items.

Reproduces the 2026-05-07 bug: AI started emitting `F-020-01：…` style
sub-numbered descriptions (treating it as a child of F-020). The old regex
extracted `F-020`, causing every new entry to collapse onto the existing F-020
row via the `update` branch, so 伏笔管理 stopped growing.
"""
from app.routers.ai.foreshadow import foreshadow_payload_from_index_item


def test_plain_f_code_still_extracted():
    """`F-020：xxx` references existing F-020; code must be extracted."""
    payload = foreshadow_payload_from_index_item(
        {"description": "F-020：苏家老宅献祭结构"}
    )
    assert payload is not None
    assert payload["code"] == "F-020"
    assert payload["description"] == "苏家老宅献祭结构"


def test_full_width_colon_and_parenthesis_format():
    """Bootstrap-style `F-024（描述, ch_NN回收）` must be cleanly parsed."""
    payload = foreshadow_payload_from_index_item(
        {"description": "F-024（离火魂印的本源损耗，ch_100回收）"}
    )
    assert payload is not None
    assert payload["code"] == "F-024"
    assert payload["planned_resolve_chapter"] == 100


def test_sub_numbered_code_does_not_collapse_to_parent():
    """`F-020-01：xxx` must NOT be parsed as `F-020`.

    Regression: before the 2026-05-07 fix, the regex's `(?![0-9])` lookahead
    only blocked trailing digits, not `-` or `_`. So `F-020-01` matched
    `F-020`, every sub-numbered foreshadow updated the same parent row, and
    no new rows were ever inserted. Now the lookahead `(?![0-9\\-_])` makes
    sub-numbered tokens fall through to the new-row branch.
    """
    payload = foreshadow_payload_from_index_item(
        {"description": "F-020-01：叶枫母亲的神魂本源被镇压在地宫深处。"}
    )
    assert payload is not None
    assert payload["code"] is None, (
        "F-020-01 must not be collapsed onto F-020; "
        "code should be None so sync_chapter_index_foreshadows assigns a fresh F-NNN."
    )
    assert payload["description"] == "叶枫母亲的神魂本源被镇压在地宫深处。"


def test_sub_numbered_underscore_variant():
    payload = foreshadow_payload_from_index_item(
        {"description": "F-021_2：陆辰被太初火种吞噬的神魂本源中带有毒火。"}
    )
    assert payload is not None
    assert payload["code"] is None
    assert payload["description"] == "陆辰被太初火种吞噬的神魂本源中带有毒火。"


def test_inline_f_code_in_chinese_prose():
    """Tail mention like `回收F-003` must still extract F-003 (\\b unaware of CJK)."""
    payload = foreshadow_payload_from_index_item(
        {"description": "本章主角回收F-003定亲信物的真相"}
    )
    assert payload is not None
    assert payload["code"] == "F-003"


def test_no_f_code_returns_none_code():
    """Brand-new foreshadow without an F-code: code is None, description preserved."""
    payload = foreshadow_payload_from_index_item(
        {"description": "少年腰间玉佩内透出古怪光泽，似与远方某座古阵呼应。"}
    )
    assert payload is not None
    assert payload["code"] is None
    assert "玉佩" in payload["description"]


# ── 新格式：显式 code 字段（_split_foreshadow_updates 产出）────────────────


def test_explicit_code_field_takes_priority_over_regex():
    """显式 code 字段存在时直接使用，无需从 description 文本中提取。"""
    payload = foreshadow_payload_from_index_item(
        {"code": "F-015", "description": "苍玄印的第三封印尚未解开", "planned_action": "develop"}
    )
    assert payload is not None
    assert payload["code"] == "F-015"
    assert payload["description"] == "苍玄印的第三封印尚未解开"
    # 显式 code 存在时，description 不应再被正则截断
    assert "苍玄印" in payload["description"]


def test_explicit_code_resolve_action():
    """resolve action + 显式 code：planned_action 应为 resolve。"""
    payload = foreshadow_payload_from_index_item(
        {"code": "F-003", "description": "定亲信物的真相已在本章揭露", "planned_action": "resolve"},
        default_status="resolved",
    )
    assert payload is not None
    assert payload["code"] == "F-003"
    assert payload["planned_action"] == "resolve"


def test_explicit_code_lay_action_no_description_prefix():
    """lay action 新埋伏笔：code=None，description 保持完整不被清洗。"""
    payload = foreshadow_payload_from_index_item(
        {"code": None, "description": "玉佩内的古纹在主角突破时发出共鸣，来历不明。", "planned_action": "develop"},
        default_status="open",
    )
    assert payload is not None
    assert payload["code"] is None
    assert "共鸣" in payload["description"]


def test_explicit_code_normalized_format():
    """显式 code 已由 _split_foreshadow_updates 规范化为 F-NNN，此处直接通过。"""
    payload = foreshadow_payload_from_index_item(
        {"code": "F-042", "description": "北境冰魄剑胚的下落"}
    )
    assert payload is not None
    assert payload["code"] == "F-042"
