"""fanfic_canon_synopsis 解析与校验。"""
from app.services.bootstrap.fanfic_canon_synopsis import _normalize_options


def test_normalize_options_filters_short_and_assigns_ids():
    raw = [
        {"label": "主线", "synopsis": "短"},
        {"label": "人物", "synopsis": "甲" * 80},
        {"label": "体系", "synopsis": "乙" * 100},
        {"label": "结局", "synopsis": "丙" * 120},
    ]
    out = _normalize_options(raw)
    assert len(out) == 3
    assert out[0]["id"] == "opt_1"
    assert out[0]["label"] == "人物"
    assert len(out[0]["synopsis"]) >= 80


def test_normalize_options_caps_at_three():
    raw = [{"label": f"第{i}", "synopsis": "x" * 90} for i in range(5)]
    out = _normalize_options(raw)
    assert len(out) == 3
