"""BeatContract 单一五拍事实源。"""
from types import SimpleNamespace

from app.services.dabai.prose.beat_contract import (
    format_execution_block,
    format_outline_constraints_block,
    resolve_beats,
)
from app.services.dabai.prose.prompt_assemble import build_prose_prompt


def _chapter(**kwargs):
    defaults = {
        "chapter_number": 1,
        "title": "开局",
        "yaqu_setup": "雨中拖尸被管事克扣",
        "emotion_turn": "发现养魂珠",
        "yinbao": "幡面异动",
        "shuang_payoff": "认主",
        "end_hook": "夜里有人窥视",
        "shuang_type": "憋屈",
        "location": "乱葬岗",
        "witnesses": ["路人甲"],
        "realm_rank": 1,
        "is_big_beat": False,
        "expected_words": 2000,
        "involved_characters": [],
        "golden_finger": {},
        "power_ladder": {},
        "characters": [],
        "positioning": {},
        "benchmark": {},
        "logline": "收尸弟子得万魂幡",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _project():
    return SimpleNamespace(
        title="万魂幡",
        logline="收尸弟子得万魂幡",
        golden_finger={"name": "万魂幡", "core_ability": "收魂"},
        power_ladder={"levels": [{"name": "炼气"}]},
        characters=[SimpleNamespace(name="沈烬", role="主角")],
        positioning={},
        benchmark={},
    )


def test_prewarn_replaces_raw_yaqu_in_prompt():
    ch = _chapter()
    pre = {
        "beat_execution": {
            "yaqu": "刑堂盘问私藏尸气",
            "trigger": "管事栽赃",
            "yinbao": "幡灵低语",
            "payoff": "反将一军",
            "hook": "孙德胜冷笑离去",
        }
    }
    project = _project()
    project.benchmark = {
        "adaptation_plan": {
            "chapter_beat_hints": [{"span": "1", "ref_beat": "禁地劳作", "must_hit": "压迫"}],
        },
    }
    _, user = build_prose_prompt(
        project, ch, pre_warn_block="导演单", pre_warn_result=pre,
    )
    assert "五拍执行" in user
    assert "刑堂盘问私藏尸气" in user
    assert "对标改编" in user
    assert "情节结果约束" in user
    assert "雨中拖尸被管事克扣" not in user
    assert "憋屈铺垫" not in user


def test_outline_fallback_keeps_full_beats():
    ch = _chapter()
    _, user = build_prose_prompt(_project(), ch)
    assert "本章爽点节拍" in user
    assert "雨中拖尸被管事克扣" in user


def test_format_execution_block():
    ch = _chapter()
    contract = resolve_beats(ch, {"beat_execution": {"yaqu": "换写法憋屈"}})
    block = format_execution_block(contract)
    assert contract.source == "prewarn"
    assert "换写法憋屈" in block


def test_outline_constraints_omit_yaqu_mandatory():
    ch = _chapter()
    block = format_outline_constraints_block(ch)
    assert "情节结果约束" in block
    assert "雨中" not in block
