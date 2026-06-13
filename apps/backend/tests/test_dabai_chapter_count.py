"""章纲数量校验：防止 LLM 只回部分章（如 9/30）仍被落库。"""
from __future__ import annotations

from dabai.schemas import expected_count_from_meta, validate_chapter_coverage, validate_step


def _chapter(num: int) -> dict:
    return {
        "chapter_number": num,
        "title": f"第{num}章",
        "shuang_type": "打脸",
        "location": "演武场·比斗",
        "yaqu_setup": "被当众羞辱克扣灵石，众人围观嘲笑",
        "emotion_turn": "从隐忍→听到辱及亡母（触发）→杀意上涌",
        "yinbao": "万魂幡血光一闪，当场反杀",
        "shuang_payoff": "当着全场杂役的面一掌拍飞对方",
        "witnesses": ["王铁柱"],
        "end_hook": "赵管事阴着脸走来",
        "new_info_count": 1,
        "is_big_beat": False,
        "expected_words": 2000,
        "realm_rank": 1,
    }


def _beat(num: int) -> dict:
    return {
        "chapter_number": num,
        "title": f"第{num}章",
        "shuang_type": "打脸",
        "location": "乱葬岗",
        "slap_target": "赵管事",
        "realm_rank": 1,
        "is_big_beat": False,
        "one_line": "一句话节拍",
    }


def test_outline_window_end():
    from dabai.config import DabaiConfig

    cfg = DabaiConfig(volume_chapters=30, outline_expand_size=15)
    assert cfg.outline_window_end(30, 1) == 15
    assert cfg.outline_window_end(30, 16) == 30
    assert cfg.outline_window_end(30, 31) == 31  # 已超规划，不再扩窗


def test_expected_count_from_batch_meta():
    assert expected_count_from_meta({"batch_start": 1, "batch_end": 15}) == 15
    assert expected_count_from_meta({"global_start": 31, "global_end": 45}) == 15


def test_volume_chapters_rejects_partial_outline():
    meta = {"batch_start": 1, "batch_end": 15}
    data = {
        "beat_sequence": [_beat(i) for i in range(1, 16)],
        "chapter_outlines": [_chapter(i) for i in range(1, 10)],
    }
    errs = validate_step("volume_chapters", data, meta=meta)
    assert any("chapter_outlines 数量不符" in e for e in errs)


def test_chapter_outlines_batch_requires_exact_count():
    meta = {"batch_start": 1, "batch_end": 5}
    data = [_chapter(i) for i in range(1, 4)]
    errs = validate_step("chapter_outlines", data, meta=meta)
    assert any("数量不符" in e for e in errs)


def test_chapter_outlines_passes_full_batch():
    meta = {"batch_start": 1, "batch_end": 5}
    data = [_chapter(i) for i in range(1, 6)]
    assert validate_step("chapter_outlines", data, meta=meta) == []


def test_validate_chapter_coverage_quality_fields():
    meta = {"batch_start": 1, "batch_end": 1}
    ch = _chapter(1)
    ch["yaqu_setup"] = "短"
    ch["emotion_turn"] = ""
    errs = validate_chapter_coverage("chapter_outlines", [ch], meta)
    assert any("yaqu_setup" in e for e in errs)
    assert any("emotion_turn" in e for e in errs)
