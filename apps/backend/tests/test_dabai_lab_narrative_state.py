"""dabai 情节状态块：时间轴/承接/批间章纲回灌。"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.dabai.lab_narrative_state import (
    format_bridge_from_outline,
    format_generated_outlines_block,
)


def test_format_generated_outlines_block_lists_beats():
    block = format_generated_outlines_block([
        {
            "chapter_number": 2,
            "title": "测试章",
            "location": "演武场",
            "shuang_type": "打脸",
            "yaqu_setup": "被辱",
            "emotion_turn": "扳机",
            "yinbao": "出手",
            "shuang_payoff": "众人惊",
            "end_hook": "更强敌人",
            "realm_rank": 1,
            "witnesses": ["甲"],
        },
    ])
    assert "第2章" in block
    assert "演武场" in block
    assert "更强敌人" in block


def test_format_bridge_from_outline_dict():
    block = format_bridge_from_outline(
        {
            "chapter_number": 5,
            "title": "上一章",
            "yaqu_setup": "憋屈",
            "end_hook": "钩子来了",
        },
        6,
    )
    assert "第6章" in block
    assert "钩子来了" in block


def test_format_bridge_from_outline_fallback_tail():
    block = format_bridge_from_outline({}, 3, "末钩兜底")
    assert "末钩兜底" in block
    assert "第3章" in block


def test_build_story_so_far_delegates_before_chapter():
    """增量补全：before = offset + start_chapter，而非仅 offset。"""
    from app.services.dabai.lab_narrative_state import build_story_so_far

    calls: list[int] = []

    def fake_narrative(db, project, *, before_chapter, prev_volume=None, extra_blocks=None):
        calls.append(before_chapter)
        return "ok"

    import app.services.dabai.lab_narrative_state as mod

    orig = mod.build_narrative_state_block
    mod.build_narrative_state_block = fake_narrative
    try:
        p = SimpleNamespace(id="x", volumes=[SimpleNamespace(volume_number=1)])
        vol = SimpleNamespace(volume_number=1)
        build_story_so_far(None, p, vol, 0, start_chapter=11)
        assert calls == [11]
    finally:
        mod.build_narrative_state_block = orig
