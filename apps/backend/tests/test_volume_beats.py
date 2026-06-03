"""卷级节拍 normalize / prompt / linter 单测。"""
from app.services.bootstrap.volume_beats import (
    apply_volume_beat_fields,
    build_volume_beat_draft_block,
    build_volume_beat_expand_block,
    normalize_beat_highlights,
)
from app.services.outline_linter.helpers import ChapterSnapshot
from app.services.outline_linter.rules_volume_beats import lint_volume_beats


def test_normalize_beat_highlights_clamps_chapter():
    raw = [{"chapter_hint": 99, "description": "林凡击败陆青云", "beat_type": "face_slap"}]
    out = normalize_beat_highlights(raw, 30)
    assert len(out) == 1
    assert out[0]["chapter_hint"] == 30


def test_apply_volume_beat_fields_sets_highlight():
    vol = {
        "planned_chapters": 30,
        "beat_highlights": [
            {
                "chapter_hint": 10,
                "beat_type": "face_slap",
                "description": "当众击败陆青云",
                "payoff_of": "退婚线",
            },
            {
                "chapter_hint": 20,
                "beat_type": "reveal",
                "description": "揭开血指印",
                "payoff_of": "",
            },
        ],
        "volume_climax": {"chapter_hint": 28, "description": "与长老决战"},
        "pacing_skeleton": "1-5密钩/10燃/28高潮",
    }
    extra: dict = {"planned_chapters": 30}
    highlight = apply_volume_beat_fields(vol, extra)
    assert highlight == "与长老决战"
    assert len(extra["beat_highlights"]) == 2
    assert extra["volume_climax"]["chapter_hint"] == 28


def test_align_redistributes_degenerate_all_last_chapter():
    """LLM 把所有节拍填成卷末同一章（60 章卷全填 60）应被确定性重排。"""
    vol = {
        "planned_chapters": 60,
        "beat_highlights": [
            {"chapter_hint": 60, "beat_type": "face_slap", "description": "重力天梯反超陆雷"},
            {"chapter_hint": 60, "beat_type": "face_slap", "description": "禁地反杀陆雷突破"},
            {"chapter_hint": 60, "beat_type": "face_slap", "description": "内门选拔击败天骄"},
        ],
        "volume_climax": {"chapter_hint": 60, "description": "宗门大比越级斩杀陆苍"},
        "emotional_turning_point": {"chapter_hint": 60, "description": "禁地共患难情定姬如雪"},
    }
    extra: dict = {"planned_chapters": 60}
    apply_volume_beat_fields(vol, extra)
    bh = [b["chapter_hint"] for b in extra["beat_highlights"]]
    cl = extra["volume_climax"]["chapter_hint"]
    tn = extra["emotional_turning_point"]["chapter_hint"]
    assert len(set(bh)) == 3 and bh == sorted(bh)
    assert all(b < cl for b in bh)
    assert min(bh[i + 1] - bh[i] for i in range(len(bh) - 1)) >= 3
    assert 0.6 * 60 <= cl <= 60
    assert 0.3 * 60 <= tn < cl


def test_align_preserves_good_distribution():
    """已分布良好的章号应原样保留。"""
    vol = {
        "planned_chapters": 30,
        "beat_highlights": [
            {"chapter_hint": 7, "beat_type": "power_up", "description": "a"},
            {"chapter_hint": 14, "beat_type": "face_slap", "description": "b"},
            {"chapter_hint": 21, "beat_type": "reveal", "description": "c"},
        ],
        "volume_climax": {"chapter_hint": 27, "description": "x"},
        "emotional_turning_point": {"chapter_hint": 16, "description": "y"},
    }
    extra: dict = {"planned_chapters": 30}
    apply_volume_beat_fields(vol, extra)
    assert [b["chapter_hint"] for b in extra["beat_highlights"]] == [7, 14, 21]
    assert extra["volume_climax"]["chapter_hint"] == 27
    assert extra["emotional_turning_point"]["chapter_hint"] == 16


def test_expand_block_lists_batch_beats():
    class Vol:
        summary = "林凡逆袭"
        conflict = "宗门压迫"
        extra = {
            "planned_chapters": 30,
            "beat_highlights": [
                {"chapter_hint": 8, "beat_type": "face_slap", "description": "击败陆青云"},
            ],
            "volume_climax": {"chapter_hint": 28, "description": "长老决战"},
            "pacing_skeleton": "前紧后松",
        }

    block = build_volume_beat_expand_block(Vol(), 1, 15)
    assert "燃点" in block
    assert "击败陆青云" in block
    assert "长老决战" in block or "第28章" in block


def test_draft_block_near_beat_chapter():
    class Vol:
        extra = {
            "planned_chapters": 30,
            "beat_highlights": [
                {"chapter_hint": 8, "beat_type": "face_slap", "description": "击败陆青云"},
            ],
            "volume_climax": {"chapter_hint": 28, "description": "长老决战"},
            "pacing_skeleton": "1-5密钩",
        }

    block = build_volume_beat_draft_block(Vol(), 8)
    assert "击败陆青云" in block
    assert build_volume_beat_draft_block(Vol(), 3) == ""


def test_linter_vb08_monotone_beat_types():
    """≥3 条燃点全为同一类型应触发 VB-08（爽感单一）。"""
    extra = {
        "planned_chapters": 60,
        "beat_highlights": [
            {"chapter_hint": 11, "beat_type": "face_slap", "description": "重力天梯反超陆雷"},
            {"chapter_hint": 34, "beat_type": "face_slap", "description": "禁地反杀陆雷夺草"},
            {"chapter_hint": 50, "beat_type": "face_slap", "description": "内门选拔击败天骄"},
        ],
        "volume_climax": {"chapter_hint": 53, "description": "宗门大比越级斩杀陆苍"},
    }
    chapters = [
        ChapterSnapshot(
            id=f"c{n}", sort_order=n - 1, title=f"第{n}章", summary="x", hook="",
            highlight="", conflict="", pacing="normal", phase="rising",
            expected_words=2300, storyline_ids=[], involved_character_ids=[],
            power_milestone=None, extra={},
        )
        for n in (11, 34, 50, 53)
    ]
    issues = lint_volume_beats(chapters, extra, planned_chapters=60)
    assert "VB-08" in [i.rule_id for i in issues]


def test_linter_vb03_missing_overlap():
    extra = {
        "planned_chapters": 30,
        "beat_highlights": [
            {
                "chapter_hint": 8,
                "beat_type": "face_slap",
                "description": "林凡在丹房炼出仙丹震惊全宗",
                "payoff_of": "",
            },
        ],
        "volume_climax": {"chapter_hint": 28, "description": "长老决战"},
    }
    chapters = [
        ChapterSnapshot(
            id="c8",
            sort_order=7,
            title="第8章",
            summary="主角去集市买菜",
            hook="天气很好",
            highlight="回家吃饭",
            conflict="无",
            pacing="normal",
            phase="opening",
            expected_words=2300,
            storyline_ids=[],
            involved_character_ids=[],
            power_milestone=None,
            extra={"has_face_slap": False},
        ),
    ]
    issues = lint_volume_beats(chapters, extra, planned_chapters=30)
    ids = [i.rule_id for i in issues]
    assert "VB-03" in ids
