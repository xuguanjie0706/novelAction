"""记忆提取字段清洗单元测试。"""
from app.utils.memory_extract import sanitize_extracted_memory_item


def test_sanitize_strips_unknown_keys():
    item = {
        "memory_type": "event",
        "title": "标题",
        "content": "正文",
        "tags": ["林默"],
        "importance_score": 0.9,
        "hallucinated_field": True,
    }
    out = sanitize_extracted_memory_item(item)
    assert out is not None
    assert "hallucinated_field" not in out
    assert out["importance_score"] == 0.9


def test_sanitize_clamps_importance_score():
    item = {"content": "x", "importance_score": 9.9}
    assert sanitize_extracted_memory_item(item)["importance_score"] == 1.0


def test_sanitize_skips_empty_content():
    assert sanitize_extracted_memory_item({"content": "  "}) is None
    assert sanitize_extracted_memory_item("not a dict") is None


def test_sanitize_invalid_memory_type_falls_back_to_event():
    item = {"content": "x", "memory_type": "invalid_type"}
    assert sanitize_extracted_memory_item(item)["memory_type"] == "event"
