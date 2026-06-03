"""写章风格守门纯逻辑单测：反 AI 腔统计 + 情绪预算（无 DB / 无 LLM）。"""
from app.services.ai.draft_style_guard import (
    count_consecutive_depressive,
    scan_cliches,
    scan_sentence_openers,
)


def test_scan_cliches_flags_cross_chapter_high_frequency():
    # 「嘴角勾起」在 3 章各出现一次 → 命中 ≥2 章，应入禁用清单
    texts = [
        "他嘴角勾起一抹弧度，转身离开。",
        "少年嘴角勾起，眼中闪过一丝寒意。",
        "她嘴角勾起一抹冷笑，没有说话。",
    ]
    flagged = scan_cliches(texts)
    assert any("嘴角勾起" in f for f in flagged)


def test_scan_cliches_ignores_one_off():
    # 仅单章单次的偶发用词不应被禁用
    texts = ["他深吸一口气，准备迎战。", "战斗开始了。", "尘埃落定。"]
    flagged = scan_cliches(texts)
    assert all("深吸一口气" not in f for f in flagged)


def test_scan_cliches_flags_by_total_count_in_single_chapter():
    # 同一章内套话堆叠 ≥4 次也应触发
    texts = ["心中一凛。心头一震。心里一沉。心中一惊。"]
    flagged = scan_cliches(texts)
    assert any("心中一凛" in f for f in flagged)


def test_scan_sentence_openers_detects_repeated_head():
    texts = [
        "他知道这件事。他知道结局。他知道一切。",
        "他知道答案。他知道方向。他知道未来。",
    ]
    openers = scan_sentence_openers(texts, min_total=4)
    assert any("他知道" in o for o in openers)


def test_count_consecutive_depressive_counts_trailing_streak():
    tones = ["热血", "憋屈", "压抑", "虐心"]
    assert count_consecutive_depressive(tones) == 3


def test_count_consecutive_depressive_resets_on_relief():
    tones = ["憋屈", "压抑", "爽快"]
    assert count_consecutive_depressive(tones) == 0


def test_count_consecutive_depressive_handles_empty():
    assert count_consecutive_depressive([]) == 0
    assert count_consecutive_depressive(["", "热血"]) == 0
