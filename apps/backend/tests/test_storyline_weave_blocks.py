"""storyline_weave_blocks / pre_warn 单元测试。"""

from app.services.bootstrap.storyline_weave_blocks import build_storyline_weave_volumes_block
from app.services.ai.storyline_weave_engine import WeaveDirective, directive_to_storyline_moves


def test_volumes_block_from_ctx_matrix():
    ctx = {
        "storyline_weave": {
            "n_volumes": 2,
            "volume_phases": ["opening", "climax"],
            "weave_matrix": {
                "主线": [
                    {"vol_index": 0, "beat": "开局", "tension": 25, "is_active": True},
                    {"vol_index": 1, "beat": "高潮", "tension": 100, "is_active": True},
                ],
                "感情线": [
                    {"vol_index": 0, "beat": "误会", "tension": 30, "is_active": True},
                    {"vol_index": 1, "beat": "和解", "tension": 50, "is_active": True},
                ],
            },
            "crossover_nodes": [
                {"line_a": "主线", "line_b": "感情线", "at_vol": 1, "trigger": "保护暴露"},
            ],
        },
    }
    block = build_storyline_weave_volumes_block(ctx)
    assert "织网矩阵" in block
    assert "开局" in block
    assert "保护暴露" in block


def test_directive_to_storyline_moves():
    d = WeaveDirective(
        planned_beats=[],
        gap_warnings=[],
    )
    from app.services.ai.storyline_weave_engine import PlannedBeat, GapWarning

    d.planned_beats = [
        PlannedBeat(
            storyline_id="u1",
            name="主线",
            beat="并肩作战",
            tension=40,
            must_advance=True,
            gap_chapters=6,
        ),
    ]
    moves = directive_to_storyline_moves(d)
    assert len(moves) == 1
    assert moves[0].must_advance is True
    assert moves[0].suggested_beat == "并肩作战"
