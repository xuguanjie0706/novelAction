"""dabai 第1章主题定制开局 + 见证者匹配。"""

from dabai.first_chapter_opening import (
    first_chapter_opening_block,
    lint_banned_ch1_tropes,
    theme_opening_examples,
    witness_stems,
)


def test_first_chapter_opening_block_bans_tuihun():
    block = first_chapter_opening_block({
        "logline": "阴尸宗收尸弟子得万魂幡",
        "characters": [{"name": "李夜", "role": "主角", "function": "外门收尸"}],
        "golden_finger": {"name": "万魂幡", "core_ability": "收魂代修"},
    })
    assert "禁止" in block and "退婚" in block


def test_theme_hint_for_shoushi():
    hint = theme_opening_examples({"logline": "阴尸宗收尸弟子乱葬岗"})
    assert "收尸" in hint or "乱葬" in hint


def test_lint_banned_ch1_tropes():
    bad = {
        "chapter_number": 1,
        "yaqu_setup": "未婚妻当众退婚，赵横一脚踹下悬崖",
        "title": "退婚",
    }
    assert lint_banned_ch1_tropes(bad) is not None
    ok = {"chapter_number": 1, "yaqu_setup": "埋尸时被同门克扣灵石"}
    assert lint_banned_ch1_tropes(ok) is None


def test_witness_stems():
    stems = witness_stems("冷如霜（背影）")
    assert "冷如霜" in stems
    assert "狗腿子" in witness_stems("赵横的狗腿子")
