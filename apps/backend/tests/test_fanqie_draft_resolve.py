"""番茄草稿 item_id 解析：每章独立槽位。"""
from app.services.fanqie.draft_resolve import _pick_item_by_exact_title, _pick_empty_unnamed_slot


def test_exact_title_no_substring_chapter10():
    drafts = [
        {"item_id": "10", "title": "第10章：远走"},
        {"item_id": "1", "title": "第1章：开局"},
    ]
    assert _pick_item_by_exact_title(drafts, "第1章：开局", set()) == "1"
    assert _pick_item_by_exact_title(drafts, "第2章：新章", set()) == ""


def test_exclude_occupied_slot():
    drafts = [
        {"item_id": "a", "title": "未命名草稿", "word_number": 0, "index": -1, "modify_time": 100},
        {"item_id": "b", "title": "未命名草稿", "word_number": 0, "index": -1, "modify_time": 200},
    ]
    iid, _ = _pick_empty_unnamed_slot(drafts, {"b"})
    assert iid == "a"


def test_unnamed_prefers_empty_word_count():
    drafts = [
        {"item_id": "a", "title": "未命名草稿", "word_number": 500, "index": -1, "modify_time": 300},
        {"item_id": "b", "title": "未命名草稿", "word_number": 0, "index": -1, "modify_time": 100},
    ]
    iid, _ = _pick_empty_unnamed_slot(drafts, set())
    assert iid == "b"
