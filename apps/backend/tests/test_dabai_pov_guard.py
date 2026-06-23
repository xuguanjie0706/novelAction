"""大白文限知视角：导演单/分场前置门禁与质检分离计分。"""
from types import SimpleNamespace

from app.services.dabai.lab_pov_guard import (
    normalize_prewarn_pov,
    scene_plan_pov_issues,
)
from app.services.dabai.lab_debrief import _build_debrief_prompt
from app.services.dabai.lab_qc_feedback import attach_rewrite_prompt
from app.services.dabai.qc_merge import _merge_report


def test_normalize_prewarn_separates_offstage_character():
    raw = {
        "cast": [
            {"name": "李夜", "reason": "主角潜入矿道"},
            {"name": "张德旺", "reason": "在万宝阁通过法镜观察"},
        ],
        "offstage_involved": [
            {
                "name": "张德旺",
                "reason": "幕后派人试探",
                "information_channel": "打手携带的子母窥光镜传音",
            },
        ],
        "fact_lock": {"on_stage": ["李夜", "张德旺"]},
        "beat_execution": {"payoff": "李夜从打手的法镜传音中听见张德旺下令撤退"},
    }

    out = normalize_prewarn_pov(raw, protagonist="李夜")

    assert [item["name"] for item in out["cast"]] == ["李夜"]
    assert out["fact_lock"]["on_stage"] == ["李夜"]
    assert out["offstage_involved"][0]["name"] == "张德旺"
    assert "子母窥光镜" in out["offstage_involved"][0]["information_channel"]


def test_scene_plan_rejects_remote_cutaway_even_when_cast_claims_protagonist():
    plan = {
        "scenes": [{
            "order": 3,
            "name": "幕后惊惧",
            "location": "万宝阁内",
            "pov_character": "李夜",
            "characters_on_stage": ["李夜", "张德旺"],
            "event": "与此同时，万宝阁内，张德旺看着法镜，心中断定李夜是老怪转世。",
        }],
    }

    issues = scene_plan_pov_issues(plan, protagonist="李夜")

    assert issues
    assert any("远程切镜" in issue for issue in issues)


def test_scene_plan_requires_protagonist_in_every_scene():
    plan = {
        "scenes": [{
            "order": 2,
            "name": "反派密谋",
            "location": "万宝阁",
            "pov_character": "张德旺",
            "characters_on_stage": ["张德旺"],
            "event": "张德旺召集打手。",
        }],
    }

    issues = scene_plan_pov_issues(plan, protagonist="李夜")

    assert any("缺少主角" in issue for issue in issues)
    assert any("POV角色" in issue for issue in issues)


def test_scene_plan_allows_observable_distant_reaction():
    plan = {
        "scenes": [{
            "order": 3,
            "name": "擂台收尾",
            "location": "执事堂广场",
            "pov_character": "李夜",
            "characters_on_stage": ["李夜", "赵狂"],
            "event": "李夜从擂台远远看到赵狂捏碎茶杯、霍然起身，只能判断对方杀意暴涨。",
        }],
    }

    assert scene_plan_pov_issues(plan, protagonist="李夜") == []


def _good_llm(**extra):
    data = {
        "continuity_score": 95,
        "hook_score": 90,
        "naturalness_score": 85,
        "beats": {k: "pass" for k in ("yaqu", "trigger", "yinbao", "payoff", "hook")},
        "chapter_suggestions": [],
    }
    data.update(extra)
    return data


def test_blocker_preserves_raw_quality_score():
    rule = {"status": "ok", "overall_score": 100, "blockers": [], "warnings": []}
    llm = _good_llm(critical_violations=[{"kind": "pov", "message": "切到幕后视角"}])

    report = _merge_report(rule, llm, "ok")

    assert report["status"] == "blocked"
    assert report["overall_score"] == 40
    assert report["raw_score"] >= 90


def test_llm_failure_is_unverified_instead_of_false_100():
    rule = {"status": "ok", "overall_score": 100, "blockers": [], "warnings": []}

    report = _merge_report(rule, None, "error")

    assert report["status"] == "unverified"
    assert report["overall_score"] == 0
    assert report["raw_score"] == 100
    assert report["warnings"][0]["rule_id"] == "DBQ-00"
    assert attach_rewrite_prompt(report)["rewrite_prompt"] == ""


def test_llm_failure_keeps_deterministic_blocker_blocked():
    rule = {
        "status": "blocked",
        "overall_score": 40,
        "blockers": [{"rule_id": "DLB-07", "message": "命中殊不知"}],
        "warnings": [],
    }

    report = _merge_report(rule, None, "parse_error")

    assert report["status"] == "blocked"
    assert report["overall_score"] == 40
    assert report["llm_status"] == "parse_error"


def test_debrief_does_not_promote_offstage_cutaway_to_protagonist_knowledge():
    project = SimpleNamespace(title="测试书", logline="", characters=[])
    chapter = SimpleNamespace(chapter_number=11, title="跟踪", content="正文")

    _, user = _build_debrief_prompt(project, chapter, [], "")

    assert "主角合理已知" in user
    assert "幕后切镜" in user
