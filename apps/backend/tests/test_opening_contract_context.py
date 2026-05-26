"""opening_contract_context 单测。"""

from app.services.ai.opening_contract_context import (
    build_opening_contract_draft_block,
    build_opening_contract_expand_block,
    is_opening_contract_window,
)


_SAMPLE = {
    "first_200_words_test": "落地林凡被退婚的羞辱场景",
    "chapter1_hook": "信物上的血指印是谁留下的",
    "chapter3_payoff": "林凡当众炼出二品丹，打脸陆青云",
    "chapter5_foreshadow": "长老密室里的上古阵图",
    "chapter10_subscribe_reason": "执法队首领竟是林凡失散兄长",
    "chapter_rhythm": "1-2快，3爽，4-5埋，6-9压，10爆",
    "opening_traps_to_avoid": ["开局纯修炼无冲突", "现代术语出戏"],
}


def test_is_opening_contract_window():
    assert is_opening_contract_window(0, 1) is True
    assert is_opening_contract_window(0, 10) is True
    assert is_opening_contract_window(0, 11) is False
    assert is_opening_contract_window(1, 5) is False


def test_draft_block_ch1_includes_first_200_and_continuity():
    block = build_opening_contract_draft_block(
        _SAMPLE,
        1,
        vol1_summary="林凡在宗门底层挣扎",
        vol1_conflict="退婚与执法队压迫",
    )
    assert "前200字" in block
    assert "林凡" in block
    assert "第1章末钩子" in block
    assert "信物上的血指印" in block
    assert "必须避开的开局坑" in block


def test_draft_block_ch3_emphasizes_payoff():
    block = build_opening_contract_draft_block(
        _SAMPLE,
        3,
        prev_chapter_tail="陆青云冷笑离去，林凡握紧拳头。",
        outline_summary="林凡在丹房绝地反击",
    )
    assert "第3章小爽点" in block
    assert "上章结尾状态" in block
    assert "陆青云" in block
    assert "first_200" not in block.lower() or "前200字核验" not in block


def test_draft_block_ch10_subscribe_hook():
    block = build_opening_contract_draft_block(_SAMPLE, 10)
    assert "第10章订阅钩" in block
    assert "执法队首领" in block


def test_expand_block_first_volume_batch():
    block = build_opening_contract_expand_block(
        _SAMPLE,
        1,
        10,
        vol1_summary="宗门底层逆袭",
        vol1_conflict="退婚羞辱",
        vol1_hook="血指印之谜",
    )
    assert "章纲必须对齐" in block
    assert "promise_fulfilled" in block
    assert "血指印" in block
    assert "第3章小爽点" in block


def test_expand_block_skips_after_ch10():
    assert build_opening_contract_expand_block(_SAMPLE, 11, 30) == ""
