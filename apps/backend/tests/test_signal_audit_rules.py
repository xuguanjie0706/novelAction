"""signal_audit 规则审计单测。"""
from app.services.bootstrap.steps.fanqie.signal_audit import _build_signal_audit_by_rules


def _base_ctx() -> dict:
    return {
        "fanqie_positioning": {
            "genre_archetype": "废柴逆袭",
            "platform_tags": ["玄幻", "系统"],
            "algo_hook": "退婚现场觉醒系统",
        },
        "contrast_design": {
            "initial_state_headline": "被未婚妻当众退婚",
            "trigger_word_estimate": "650",
        },
        "face_slap_map": {"first_slap_chapter": 3},
        "rhythm_map": {"auto_dry_spells": []},
    }


def test_signal_audit_rules_all_pass():
    data = _build_signal_audit_by_rules(_base_ctx())
    assert data["overall_pass"] is True
    assert data["_generated_by"] == "rule"
    assert data["overall_score"] >= 80


def test_signal_audit_rules_fail_first_slap():
    ctx = _base_ctx()
    ctx["face_slap_map"] = {"first_slap_chapter": 8}
    data = _build_signal_audit_by_rules(ctx)
    assert data["overall_pass"] is False
    assert data["first_slap_timing_check"]["pass"] is False
