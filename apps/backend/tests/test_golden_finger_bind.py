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


def test_golden_finger_name_alone_not_awakening():
    """黄金第3章打脸戏：金手指名不应单独触发觉醒判定。"""
    ch = {
        "chapter_number": 3,
        "title": "未婚妻？你不配！",
        "yinbao": "叶辰捏碎洗髓丹，系统瞬间吸干药力转化为300点修为，修为再跳两级",
        "emotion_turn": "从【淡漠】→【发现系统能闻到丹药香气自动转化】→【戏谑】",
        "end_hook": "三天后家族大比，你敢来吗？",
    }
    assert not is_awakening_chapter(ch, golden_finger_name="万物本源吞噬系统")


def test_db_10_skips_mature_use_chapter_three():
    """熟练使用期打脸章不应误报 DB-10。"""
    cfg = DabaiConfig()
    ch = {
        "chapter_number": 3,
        "shuang_type": "打脸",
        "yaqu_setup": "苏清月当众递洗髓丹要求退婚",
        "emotion_turn": "从【淡漠】→【发现系统能闻到丹药香气自动转化】→【戏谑】",
        "yinbao": "叶辰捏碎丹药，系统吸干药力转化修为",
        "shuang_payoff": "碎渣撒在苏清月脚下，当众休妻",
        "witnesses": ["苏清月"],
        "end_hook": "叶天拔剑被约战止住",
        "new_info_count": 1,
        "realm_rank": 2,
    }
    report = lint_chapters([ch], cfg, golden_finger_name="万物本源吞噬系统")
    assert not any(i.rule_id == "DB-10" for i in report.issues)


def test_awakening_chapter_one_with_lock_signal():
    ch = {
        "chapter_number": 1,
        "yinbao": "脑海中系统倒计时归零，提示万物本源吞噬系统已锁定",
        "emotion_turn": "从屈辱→机械音→狠厉",
    }
    assert is_awakening_chapter(ch, golden_finger_name="万物本源吞噬系统")
