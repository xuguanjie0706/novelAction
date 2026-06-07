"""章纲伏笔引用解析单测。"""
from app.services.ai.foreshadow_ref import is_uuid_string, lookup_foreshadow_by_ref


def test_is_uuid_string():
    assert is_uuid_string("253f80bb-dae4-406e-8646-2e3088bb07ab")
    assert not is_uuid_string("万古吞天印初显")
    assert not is_uuid_string("")
    assert not is_uuid_string(None)


def test_coerce_string_ref():
    from app.services.ai.foreshadow_ref import _coerce_foreshadow_ref

    assert _coerce_foreshadow_ref("圣体之谜") == {
        "id": "圣体之谜",
        "description": "圣体之谜",
    }
