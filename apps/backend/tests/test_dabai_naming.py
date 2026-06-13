"""大白文人物正名：占位名检测 + 章纲 linter DB-14。"""
from dabai.config import DabaiConfig
from dabai.linter import lint_chapters
from dabai.naming import is_placeholder_character_name, lint_character_roster


def test_placeholder_names_detected():
    cases = [
        ("执法堂甲", True),
        ("执法堂乙", True),
        ("天剑宗弟子A", True),
        ("外门弟子众", True),
        ("路人甲", True),
        ("某长老", True),
        ("李天骄", False),
        ("周扒皮", False),
        ("孙长老", False),
        ("赵铁柱", False),
    ]
    for name, bad in cases:
        reason = is_placeholder_character_name(name)
        assert (reason is not None) == bad, f"{name}: {reason}"


def test_lint_character_roster():
    bad = lint_character_roster([
        {"name": "林凡"},
        {"name": "执法堂甲"},
        {"name": "天剑宗弟子B"},
    ])
    assert len(bad) == 2


def test_db14_witness_placeholder():
    cfg = DabaiConfig()
    ctx = {"characters": [{"name": "林凡"}, {"name": "李天骄"}]}
    ch = {
        "chapter_number": 1,
        "shuang_type": "打脸",
        "yaqu_setup": "被羞辱",
        "emotion_turn": "从隐忍→听到辱及亡母（触发）→杀意上涌",
        "shuang_payoff": "当众打脸",
        "witnesses": ["执法堂甲"],
        "end_hook": "更强敌人现身",
        "new_info_count": 1,
        "realm_rank": 1,
    }
    report = lint_chapters([ch], cfg, ctx=ctx)
    assert any(i.rule_id == "DB-14" for i in report.issues)
