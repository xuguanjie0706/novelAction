"""gate_auto 单元测试。"""

from types import SimpleNamespace

from app.services.bootstrap.gate_auto import (
    build_auto_resume_payload,
    is_auto_mode,
    merge_gate_data_snapshot,
    merge_gate_data_with_auto_mode,
)


def test_is_auto_mode():
    assert is_auto_mode({"auto_mode": True})
    assert not is_auto_mode({})
    assert not is_auto_mode(None)


def test_merge_gate_data():
    assert merge_gate_data_with_auto_mode({"kind": "x"}, True)["auto_mode"] is True
    assert "auto_mode" not in merge_gate_data_with_auto_mode({"auto_mode": True}, False)


def test_merge_gate_data_with_llm_provider():
    merged = merge_gate_data_with_auto_mode(
        None, True, llm_provider_id="550e8400-e29b-41d4-a716-446655440000",
    )
    assert merged["auto_mode"] is True
    assert "llm_provider_id" in merged


def test_merge_gate_data_snapshot_preserves_auto_mode():
    """回归：立项 gate 落库不得抹掉创建 run 时的 auto_mode。"""
    merged = merge_gate_data_snapshot(
        {"auto_mode": True},
        {
            "kind": "positioning",
            "positioning": {"selling_point": "逆袭"},
            "logline": "测试",
        },
    )
    assert merged["auto_mode"] is True
    assert merged["kind"] == "positioning"


def test_build_auto_resume_positioning():
    run = SimpleNamespace(
        id="r1",
        status="awaiting_gate",
        mode="sequential",
        gate_data={
            "kind": "positioning",
            "positioning": {
                "target_audience": "男频玄幻",
                "tropes": ["玄幻"],
                "reference_works": ["斗破"],
                "selling_point": "逆袭爽文",
                "face_slap_pattern": "高频",
                "emotional_arc": "逆袭",
                "pace_type": "快",
                "taboo_lines": ["无绿帽"],
            },
        },
    )
    payload = build_auto_resume_payload(run)
    assert payload and payload.get("action") == "approve"
    assert payload.get("positioning")


def test_build_auto_resume_retry_not_auto():
    """自动模式不再对失败步骤自动 retry_step。"""
    run = SimpleNamespace(
        id="r2",
        status="awaiting_retry",
        mode="sequential",
        gate_data={"kind": "step_retry", "step": "characters"},
    )
    assert build_auto_resume_payload(run) is None
