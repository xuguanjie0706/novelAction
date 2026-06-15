"""lab_realm_baseline 单元测试 — 境界情节驱动解析与导演单后处理。"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.dabai.lab_realm_baseline import (
    build_writing_realm_block,
    parse_realm_label,
    sanitize_prewarn_realm,
)
from app.services.dabai.lab_realm_baseline import RealmBaseline


def _project(levels=None):
    return SimpleNamespace(
        power_ladder={
            "levels": levels or [
                {"rank": 1, "name": "炼气境"},
                {"rank": 2, "name": "筑基境"},
            ],
        },
        meta={},
    )


def test_parse_lianqi_third_layer():
    p = _project()
    out = parse_realm_label("沈砚直达炼气境三重！", p)
    assert out is not None
    assert out["sub_level"] == 3
    assert "炼气境" in out["label"]


def test_parse_lianqi_legacy_major():
    p = _project()
    out = parse_realm_label("炼气境一重", p)
    assert out is not None
    assert out["sub_level"] == 1
    assert out["major_rank"] == 1


def test_writing_realm_block_no_hard_cap():
    p = _project()
    ch = SimpleNamespace(
        realm_rank=1,
        yinbao="黄泉本源气灌体，直达炼气境三重",
        shuang_payoff="",
        emotion_turn="",
        title="",
    )
    baseline = RealmBaseline(
        label="炼气境·第1层",
        major_name="炼气境",
        major_rank=1,
        sub_level=1,
        source="第1章末面板",
        source_chapter=1,
    )
    block = build_writing_realm_block(p, ch, baseline)
    assert "情节为准" in block
    assert "禁止本章内乱跳档" not in block
    assert "五拍规划章末" in block
    assert "三重" in block or "第3层" in block


def test_sanitize_prewarn_fixes_stall_after_surge():
    p = _project()
    ch = SimpleNamespace(
        yinbao="修为瞬间从一层巅峰连破两级，直达炼气境三重",
        shuang_payoff="",
        emotion_turn="",
        title="",
    )
    baseline = RealmBaseline(
        label="炼气境·第1层",
        major_name="炼气境",
        major_rank=1,
        sub_level=1,
        source="panel",
    )
    raw = {
        "fact_lock": {"realm": "炼气境", "realm_end": ""},
        "beat_execution": {
            "yinbao": "本源气冲刷，暴涨后稳固在炼气境一层巅峰",
        },
    }
    out = sanitize_prewarn_realm(raw, p, ch, baseline)
    assert out["fact_lock"]["realm"] == "炼气境·第1层"
    assert out["fact_lock"]["realm_sub_rank"] == 1
    assert "三重" in out["fact_lock"]["realm_end"] or "第3层" in out["fact_lock"]["realm_end"]
    assert "一层巅峰" not in out["beat_execution"]["yinbao"]
