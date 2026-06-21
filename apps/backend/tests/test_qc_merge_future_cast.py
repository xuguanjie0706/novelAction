"""qc_merge — LLM 跨章边界 future_cast_violations 合并。"""
from __future__ import annotations

from app.services.dabai.qc_merge import _merge_report


def test_merge_no_future_cast_violations():
    rule = {"status": "ok", "overall_score": 100, "blockers": [], "warnings": []}
    llm = {
        "continuity_score": 90,
        "hook_score": 85,
        "beats": {k: "pass" for k in ("yaqu", "trigger", "yinbao", "payoff", "hook")},
        "future_cast_violations": [],
    }
    out = _merge_report(rule, llm, "ok")
    assert out["status"] != "blocked"
    assert out["overall_score"] > 80


def test_merge_future_cast_violation_blocks():
    rule = {"status": "warning", "overall_score": 90, "blockers": [], "warnings": []}
    llm = {
        "continuity_score": 90,
        "hook_score": 85,
        "beats": {k: "pass" for k in ("yaqu", "trigger", "yinbao", "payoff", "hook")},
        "future_cast_violations": [
            {"name": "王铁柱", "reason": "正文写其被赵狂当场斩首，魂飞魄散"},
        ],
    }
    out = _merge_report(rule, llm, "ok")
    assert out["status"] == "blocked"
    assert out["overall_score"] == 40
    assert out["blockers"][0]["rule_id"] == "DBQ-05"


def test_merge_endhook_paste_debounce_hook_partial():
    """末段复读 end_hook 时 hook 不应再标 partial（与 DBQ-04 双扣）。"""
    rule = {"status": "ok", "overall_score": 100, "blockers": [], "warnings": []}
    llm = {
        "continuity_score": 90,
        "hook_score": 60,
        "beats": {
            "yaqu": "pass", "trigger": "pass", "yinbao": "pass",
            "payoff": "pass", "hook": "partial",
        },
        "repetition_issue": "末段复读章纲 end_hook 原句，收束段已完成",
    }
    out = _merge_report(rule, llm, "ok")
    assert out["llm"]["beats"]["hook"] == "pass"
    assert not any(
        "章末钩子" in w.get("message", "")
        for w in out["warnings"]
        if w.get("rule_id") == "DBQ-02"
    )
    assert any(w.get("rule_id") == "DBQ-04" for w in out["warnings"])
