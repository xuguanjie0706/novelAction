"""第1章开局 + benchmark 对标改编。"""
from dabai.first_chapter_opening import (
    first_chapter_opening_block,
    lint_banned_ch1_tropes,
    lint_ch1_cliche_template,
    prose_opening_cliche_hit,
    theme_opening_examples,
    witness_stems,
)
from dabai.plot_blueprint import ch1_opening_guidance_block


def test_first_chapter_opening_block_bans_tuihun():
    block = first_chapter_opening_block({
        "logline": "阴尸宗收尸弟子得万魂幡",
        "characters": [{"name": "李夜", "role": "主角", "function": "外门收尸"}],
        "golden_finger": {"name": "万魂幡", "core_ability": "收魂代修"},
    })
    assert "禁止" in block and "退婚" in block


def test_ch1_opening_prefers_benchmark():
    ctx = {
        "logline": "阴尸宗收尸弟子",
        "benchmark": {
            "reference_books": [{"title": "某魔门爆款", "plot_role_in_adaptation": "开篇母版"}],
            "adaptation_plan": {
                "strategy": "主借《某魔门爆款》开篇弧",
                "chapter_beat_hints": [
                    {"span": "1-3", "ref_beat": "禁地劳作", "must_hit": "法宝异动+首次压迫"},
                ],
            },
            "plot_blueprints": [{
                "title": "某魔门爆款",
                "plot_skeleton": {"opening_arc": [{"span": "1-5章", "beats": "差事现场→羞辱→异宝露头"}]},
            }],
        },
    }
    block = ch1_opening_guidance_block(ctx)
    assert "对标改编" in block
    assert "某魔门爆款" in block
    hint = theme_opening_examples(ctx)
    assert "某魔门爆款" in hint or "禁地劳作" in hint


def test_theme_fallback_without_benchmark():
    hint = theme_opening_examples({"logline": "阴尸宗收尸弟子乱葬岗"})
    assert "退婚" in hint or "差事" in hint or "阴秽" in hint


def test_lint_banned_ch1_tropes():
    bad = {
        "chapter_number": 1,
        "yaqu_setup": "未婚妻当众退婚，赵横一脚踹下悬崖",
        "title": "退婚",
    }
    assert lint_banned_ch1_tropes(bad) is not None
    ok = {"chapter_number": 1, "yaqu_setup": "在刑堂被盘问为何私藏尸气"}
    assert lint_banned_ch1_tropes(ok) is None


def test_lint_ch1_cliche_template():
    template = {
        "chapter_number": 1,
        "yaqu_setup": "沈烬拖着残躯在雨中收尸，管事厉刚克扣养魂珠，还踩在他冻疮的手背上",
        "title": "开局",
    }
    assert lint_ch1_cliche_template(template) is not None
    mild = {"chapter_number": 1, "yaqu_setup": "在刑堂被盘问为何私藏尸气"}
    assert lint_ch1_cliche_template(mild) is None


def test_prose_opening_cliche_hit():
    opening = "冰冷粘稠的雨水混着泥沙。管事厉刚克扣了三枚养魂珠，一脚踩在他满是冻疮的手背上。"
    assert prose_opening_cliche_hit(opening) is not None


def test_prose_cliche_skipped_when_benchmark():
    opening = "冰冷粘稠的雨水混着泥沙。管事厉刚克扣了三枚养魂珠，一脚踩在他满是冻疮的手背上。"
    ctx = {
        "benchmark": {
            "adaptation_plan": {
                "chapter_beat_hints": [{"span": "1-3", "ref_beat": "差事压迫", "must_hit": "法宝异动"}],
            },
        },
    }
    assert prose_opening_cliche_hit(opening, ctx=ctx) is None
    assert lint_ch1_cliche_template(
        {"chapter_number": 1, "yaqu_setup": "雨中收尸管事克扣养魂珠踩手背"},
        ctx=ctx,
    ) is None


def test_witness_stems():
    stems = witness_stems("冷如霜（背影）")
    assert "冷如霜" in stems
    assert "狗腿子" in witness_stems("赵横的狗腿子")
