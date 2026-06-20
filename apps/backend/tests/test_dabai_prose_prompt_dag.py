"""正文 prompt DAG：块顺序与 plot_blueprint 隔离。"""
from types import SimpleNamespace

from app.services.dabai.prose.prompt_assemble import build_prose_prompt
from app.services.dabai.prose.prompt_blocks import PRIORITY_RULES


def _chapter():
    return SimpleNamespace(
        chapter_number=2,
        title="试探",
        yaqu_setup="被刁难",
        emotion_turn="扳机",
        yinbao="引爆",
        shuang_payoff="小爽",
        end_hook="钩子",
        shuang_type="打脸",
        location="外门",
        witnesses=["甲"],
        realm_rank=1,
        is_big_beat=False,
        expected_words=2000,
        involved_characters=[],
    )


def _project():
    return SimpleNamespace(
        title="测试书",
        logline="测试",
        golden_finger={"name": "幡", "core_ability": "收魂"},
        power_ladder={"levels": [{"name": "炼气"}]},
        characters=[SimpleNamespace(name="主角", role="主角")],
        positioning={},
        benchmark={},
    )


def test_no_plot_blueprint_in_prose_prompt():
    _, user = build_prose_prompt(
        _project(), _chapter(),
        pre_warn_block="【写前导演单】fact",
        pre_warn_result={"beat_execution": {"yaqu": "a", "trigger": "b",
                                              "yinbao": "c", "payoff": "d", "hook": "e"}},
    )
    assert "plot_blueprint" not in user.lower()
    assert "情节蓝图" not in user


def test_priority_rules_in_system():
    system, _ = build_prose_prompt(_project(), _chapter())
    assert PRIORITY_RULES.strip() in system


def test_block_order_prewarn_before_beats():
    _, user = build_prose_prompt(
        _project(), _chapter(),
        pre_warn_block="【写前导演单】",
        pre_warn_result={"beat_execution": {"yaqu": "x", "trigger": "y",
                                            "yinbao": "z", "payoff": "p", "hook": "h"}},
    )
    pre_idx = user.index("【写前导演单】")
    beat_idx = user.index("五拍执行")
    assert pre_idx < beat_idx
