"""金手指绑定节拍：疑→证→择 模块与 DB-10 linter。"""
from dabai.config import DabaiConfig
from dabai.golden_finger_bind import (
    bind_ladder_emotion_turn_hint,
    is_awakening_chapter,
    lint_bind_ladder,
)
from dabai.linter import lint_chapters


def test_is_awakening_chapter_golden_three():
    ch = {
        "chapter_number": 1,
        "title": "系统觉醒",
        "yinbao": "吞噬系统生效",
        "end_hook": "叮",
        "shuang_type": "升级",
    }
    assert is_awakening_chapter(ch, golden_finger_name="万物吞噬系统")


def test_is_awakening_chapter_outside_golden():
    ch = {"chapter_number": 5, "title": "系统再临", "yinbao": "系统升级"}
    assert not is_awakening_chapter(ch)


def test_lint_bind_ladder_ok():
    et = bind_ladder_emotion_turn_hint("暴食系统")
    assert lint_bind_ladder(et) is None


def test_lint_bind_ladder_missing_doubt():
    assert lint_bind_ladder("从隐忍→听到侮辱→出手") is not None


def test_db_10_flags_awakening_without_bind_ladder():
    cfg = DabaiConfig()
    ch = {
        "chapter_number": 1,
        "shuang_type": "升级",
        "yaqu_setup": "被挖骨",
        "emotion_turn": "从隐忍→听到侮辱→出手",
        "yinbao": "系统觉醒",
        "shuang_payoff": "当众升级，全场震惊",
        "witnesses": ["路人"],
        "end_hook": "更强敌人",
        "new_info_count": 1,
        "realm_rank": 1,
    }
    report = lint_chapters(
        [ch], cfg, golden_finger_name="吞噬系统",
    )
    assert any(i.rule_id == "DB-10" for i in report.issues)
