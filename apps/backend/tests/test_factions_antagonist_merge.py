"""势力+卷级对立面合并节点：拆分/回退契约单测。

split_factions_antagonist_payload 决定合并响应缺哪部分时是否回退到原始独立步骤，
是合并的健壮性保证，必须锁死其行为。
"""

from app.services.bootstrap.prompts.factions_antagonist import (
    split_factions_antagonist_payload,
)


def test_split_full_object():
    data = {
        "factions": [{"name": "青云宗"}],
        "antagonist_ladder": [{"vol_index": 0, "boss_name": "王九", "faction": "青云宗"}],
    }
    factions, ladder = split_factions_antagonist_payload(data)
    assert len(factions) == 1 and len(ladder) == 1
    assert ladder[0]["faction"] == "青云宗"


def test_split_ladder_alias_key():
    data = {"factions": [{"name": "魔殿"}], "ladder": [{"vol_index": 0, "boss_name": "赵某"}]}
    factions, ladder = split_factions_antagonist_payload(data)
    assert len(factions) == 1 and len(ladder) == 1


def test_split_missing_ladder_triggers_fallback():
    # 缺 ladder → ladder 为空，合并步骤据此回退独立步骤
    factions, ladder = split_factions_antagonist_payload({"factions": [{"name": "甲"}]})
    assert factions and ladder == []


def test_split_bare_list_is_factions_only():
    factions, ladder = split_factions_antagonist_payload([{"name": "甲"}, {"name": "乙"}])
    assert len(factions) == 2 and ladder == []


def test_split_garbage_both_empty():
    assert split_factions_antagonist_payload(None) == ([], [])
    assert split_factions_antagonist_payload("oops") == ([], [])
    assert split_factions_antagonist_payload({"factions": "x", "antagonist_ladder": 3}) == ([], [])
