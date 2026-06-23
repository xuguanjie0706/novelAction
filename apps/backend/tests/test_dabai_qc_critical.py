"""硬伤质检：上帝视角/境界/战力 + merge 升格阻断。"""
from types import SimpleNamespace
from uuid import uuid4

from app.services.dabai.lab_qc_critical import (
    check_god_pov_violations,
    run_critical_rule_checks,
)
from app.services.dabai.qc_merge import _blockers_from_prefixed_suggestions, _merge_report


def test_god_pov_catches_identity_exposition():
    text = "演武场上，此人正是外门狂徒陈山，练气七层修为。"
    hits = check_god_pov_violations(text)
    assert hits
    assert hits[0]["rule_id"] == "DLB-07"
    assert "此人正是" in hits[0]["message"]


def test_god_pov_allows_dialogue_realm():
    text = "王铁柱颤声道：「陈山是练气七层，咱们认输吧？」"
    assert not check_god_pov_violations(text)


def test_prefixed_suggestions_become_blockers():
    llm = {
        "continuity_score": 95,
        "hook_score": 90,
        "beats": {k: "pass" for k in ("yaqu", "trigger", "yinbao", "payoff", "hook")},
        "naturalness_score": 85,
        "chapter_suggestions": [
            "[境界] 陈山应写练气三层",
            "[视角] 旁白直接报修为",
            "[可信] 一招废人缺铺垫",
            "见证者反应可再具体",
        ],
    }
    blockers = _blockers_from_prefixed_suggestions(llm)
    assert len(blockers) == 3
    assert blockers[0]["rule_id"] == "DBQ-08"

    rule = {"status": "warning", "overall_score": 92, "blockers": [], "warnings": []}
    report = _merge_report(rule, llm, "ok")
    assert report["status"] == "blocked"
    assert report["overall_score"] <= 40
    assert len(report["blockers"]) >= 3


def test_critical_violations_block_high_score():
    llm = {
        "continuity_score": 95,
        "hook_score": 90,
        "beats": {k: "pass" for k in ("yaqu", "trigger", "yinbao", "payoff", "hook")},
        "naturalness_score": 85,
        "critical_violations": [
            {"kind": "pov", "message": "开篇旁白报陈山身份与修为"},
        ],
        "chapter_suggestions": [],
    }
    rule = {"status": "ok", "overall_score": 100, "blockers": [], "warnings": []}
    report = _merge_report(rule, llm, "ok")
    assert report["status"] == "blocked"
    assert report["overall_score"] == 40


def test_rule_layer_god_pov_in_merge():
    content = "此人正是外门狂徒陈山，练气七层修为。李夜抬头。"
    ch = SimpleNamespace(
        chapter_number=10,
        involved_characters=["李夜", "陈山"],
        witnesses=["王铁柱"],
        realm_rank=1,
    )
    project = SimpleNamespace(
        id=uuid4(),
        characters=[
            SimpleNamespace(
                name="陈山", role="反派", tier="核心",
                start_realm="练气期七层", extra={},
            ),
            SimpleNamespace(
                name="李夜", role="主角", tier="核心",
                start_realm="练气境·第三层", extra={"current_realm": "练气境·第三层"},
            ),
        ],
        power_ladder={"levels": [{"name": "练气境", "rank": 1}]},
    )
    blockers = run_critical_rule_checks(project, ch, content, protagonist_name="李夜")
    assert any(b["rule_id"] == "DLB-07" for b in blockers)

    rule = {
        "status": "blocked",
        "overall_score": 40,
        "blockers": blockers,
        "warnings": [],
    }
    report = _merge_report(rule, None, "skipped")
    assert report["status"] == "blocked"
