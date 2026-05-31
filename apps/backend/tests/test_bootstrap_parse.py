"""Bootstrap parse_json 容错单测。"""

import json

import pytest

from app.services.bootstrap.parse import parse_json


def test_parse_json_strips_fence_and_think():
    sample = '<think>x</think>\n```json\n{"a": 1}\n```'
    assert parse_json(sample) == {"a": 1}


def test_parse_json_trailing_comma_in_array():
    raw = '[\n  {"memory_type": "setting", "title": "t", "content": "c", "tags": []},\n]'
    data = parse_json(raw)
    assert isinstance(data, list) and len(data) == 1


def test_parse_json_unquoted_keys():
    raw = '[{memory_type: "setting", title: "锚点", content: "不少于三十字的设定说明内容", tags: ["a"]}]'
    data = parse_json(raw)
    assert data[0]["memory_type"] == "setting"


def test_parse_json_truncates_trailing_prose():
    raw = '[{"a": 1}] 以上是记忆种子。'
    assert parse_json(raw) == [{"a": 1}]


def test_parse_json_repairs_suggestion_string_closed_with_bracket():
    """质检 JSON 常见笔误：数组最后一项以 \"] 而非 \" 收尾。"""
    raw = """{
  "overall_score": 8.2,
  "suggestions": [
    "第一条建议",
    "第二条建议内容较长"]
  ],
  "summary": "ok"
}"""
    data = parse_json(raw)
    assert data["overall_score"] == 8.2
    assert len(data["suggestions"]) == 2


def test_parse_json_raises_on_garbage():
    with pytest.raises(json.JSONDecodeError):
        parse_json("not json at all")


def test_parse_json_repairs_colon_newline_before_array():
    """写前预警 gemini 常见：\"key_skills\":\\n ["""
    raw = """{
  "ok": true,
  "protagonist_fact_sheet": {
    "realm": "聚火境",
    "key_skills":
 [
      "技能A"
    ]
  }
}"""
    data = parse_json(raw)
    assert data["protagonist_fact_sheet"]["key_skills"] == ["技能A"]
