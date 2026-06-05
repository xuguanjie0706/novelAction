"""跨卷全书章号起始与展示换算。"""
from app.services.bootstrap.volume_chapter_starts import (
    build_volume_global_ranges_block,
    compute_chapter_starts,
    format_volume_chapter_label,
    shift_chapter_refs_in_text,
)


def test_compute_chapter_starts_cumulative():
    assert compute_chapter_starts([30, 55, 40]) == [1, 31, 86]


def test_shift_pacing_skeleton_to_global():
    text = "1-15章杀向始源; 16-30章法则对决; 46-50章斩杀天道"
    out = shift_chapter_refs_in_text(text, 401)
    assert "401-415章" in out
    assert "416-430章" in out
    assert "446-450章" in out


def test_format_volume_chapter_label_dual():
    assert format_volume_chapter_label(15, 1) == "第 15 章"
    assert format_volume_chapter_label(15, 401) == "全书第 415 章（本卷第 15 章）"


def test_build_volume_global_ranges_block():
    block = build_volume_global_ranges_block([30, 55])
    assert "第1卷：全书约第1–30章" in block
    assert "第2卷：全书约第31–85章" in block
    assert "本卷内" in block
