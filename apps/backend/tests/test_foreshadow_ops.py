"""章纲 foreshadow_ops 结构化解析与互转。"""
from __future__ import annotations

from app.services.bootstrap.foreshadow_ops import (
    apply_chapter_foreshadow_fields,
    coerce_foreshadow_ops,
    foreshadow_summary_from_extra,
    legacy_string_to_ops,
    mystery_op_covered,
    normalize_op,
    ops_to_legacy_string,
    ops_to_node_columns,
)


def test_normalize_lay_requires_name():
    assert normalize_op({"op": "lay", "name": "青印"}) == {
        "op": "lay",
        "name": "青印",
    }
    assert normalize_op({"op": "lay", "theme": "身世"}) is None


def test_normalize_heat_resolve_accepts_code_or_note():
    assert normalize_op({"op": "heat", "code": "F-03"}) == {
        "op": "heat",
        "code": "F-03",
    }
    assert normalize_op({"op": "resolve", "note": "真相揭晓"}) == {
        "op": "resolve",
        "note": "真相揭晓",
    }


def test_legacy_string_roundtrip():
    raw = "埋[神秘玉佩|主题:主角身世] 加热[F-02+追问] 收[F-01+揭晓]"
    ops = legacy_string_to_ops(raw)
    assert len(ops) == 3
    assert ops[0] == {"op": "lay", "name": "神秘玉佩", "theme": "主角身世"}
    rendered = ops_to_legacy_string(ops)
    assert "埋[神秘玉佩|主题:主角身世]" in rendered
    assert "加热[F-02+追问]" in rendered
    assert "收[F-01+揭晓]" in rendered


def test_coerce_prefers_foreshadow_ops_over_legacy():
    item = {
        "foreshadow_ops": [{"op": "lay", "name": "结构化伏笔"}],
        "foreshadow": "埋[旧文本]",
    }
    ops = coerce_foreshadow_ops(item)
    assert ops[0]["name"] == "结构化伏笔"


def test_coerce_falls_back_to_legacy_string():
    item = {"foreshadow": "埋[黑雾源头] 收[丹火异动]"}
    ops = coerce_foreshadow_ops(item)
    assert ops[0]["op"] == "lay"
    assert ops[0]["name"] == "黑雾源头"
    assert ops[1]["op"] == "resolve"


def test_apply_chapter_foreshadow_fields_dual_write():
    item = {
        "foreshadow_ops": [
            {"op": "lay", "name": "玉佩", "theme": "身世"},
        ],
    }
    ops, legacy = apply_chapter_foreshadow_fields(item)
    assert len(ops) == 1
    assert legacy == "埋[玉佩|主题:身世]"


def test_ops_to_node_columns():
    ops = [
        {"op": "lay", "name": "玉佩", "theme": "身世"},
        {"op": "resolve", "code": "F-01", "note": "揭晓"},
    ]
    laid, resolved = ops_to_node_columns(ops)
    assert laid[0]["description"] == "玉佩"
    assert laid[0]["theme"] == "身世"
    assert resolved[0]["id"] == "F-01"


def test_foreshadow_summary_from_ops():
    extra = {
        "foreshadow_ops": [{"op": "lay", "name": "青印", "theme": "身世"}],
        "foreshadow": "埋[旧文本]",
    }
    summary = foreshadow_summary_from_extra(extra)
    assert "埋[青印|主题:身世]" in summary
    assert "旧文本" not in summary


def test_foreshadow_summary_falls_back_to_legacy():
    extra = {"foreshadow": "埋[黑雾源头]"}
    assert "黑雾源头" in foreshadow_summary_from_extra(extra)


def test_mystery_op_covered_lay_heat_resolve():
    extra = {
        "foreshadow_ops": [
            {"op": "lay", "name": "主角身世", "theme": "立意"},
            {"op": "heat", "code": "F-02", "note": "主角身世线索"},
            {"op": "resolve", "code": "F-01", "note": "主角身世揭晓"},
        ],
    }
    assert mystery_op_covered("主角身世", extra, "lay")
    assert mystery_op_covered("主角身世", extra, "heat")
    assert mystery_op_covered("主角身世", extra, "resolve")


def test_mystery_op_covered_legacy_fallback():
    extra = {"foreshadow": "埋[玉佩|主题:身世] 加热[玉佩+追问] 收[玉佩]"}
    assert mystery_op_covered("玉佩", extra, "lay")
    assert mystery_op_covered("玉佩", extra, "heat")
    assert mystery_op_covered("玉佩", extra, "resolve")
