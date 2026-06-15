"""dabai json_object 任务解析 + 金手指内层校验。"""
from app.services.llm_errors import is_response_format_rejected_error
from app.services.llm_task_profiles import resolve_response_format
from dabai.schemas import validate_step


def test_resolve_response_format_dabai_structured_steps():
    assert resolve_response_format("dabai.golden_finger") == {"type": "json_object"}
    assert resolve_response_format("dabai.quality") == {"type": "json_object"}
    assert resolve_response_format("dabai.write") is None
    assert resolve_response_format("quality.check") is None


def test_is_response_format_rejected_error():
    class _Err(Exception):
        status_code = 400

    assert is_response_format_rejected_error(
        _Err("unsupported parameter: response_format"),
    )
    assert not is_response_format_rejected_error(_Err("model not found"))


def test_golden_finger_first_10_shuang_min_eight():
    base = {
        "golden_finger": {
            "name": "测试金手指",
            "first_10_shuang": [f"爽点{i}" for i in range(7)],
        },
        "power_ladder": {"levels": [{"rank": 1, "name": "练气"}]},
        "antagonist_ladder": [{"volume_number": 1, "boss_name": "测试Boss", "motive": "仇怨"}],
    }
    errs = validate_step("golden_finger", base)
    assert any("first_10_shuang" in e for e in errs)

    ok = dict(base)
    ok["golden_finger"] = dict(base["golden_finger"])
    ok["golden_finger"]["first_10_shuang"] = [f"爽点{i}" for i in range(8)]
    assert validate_step("golden_finger", ok) == []
