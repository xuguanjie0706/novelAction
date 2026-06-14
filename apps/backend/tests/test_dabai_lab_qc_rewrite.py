"""lab 质检 rewrite_prompt 合成与 score 门控。"""
from app.services.dabai.lab_qc_feedback import (
    REWRITE_SCORE_THRESHOLD,
    attach_rewrite_prompt,
    build_lab_rewrite_prompt,
)
from app.services.dabai.lab_qc_patch import (
    build_qc_patch_prompt,
    report_actionable_for_patch,
)


def test_build_qc_patch_prompt_chapter_only():
    ch = type("Ch", (), {
        "chapter_number": 3,
        "title": "打脸",
        "end_hook": "神秘人现身",
        "expected_words": 2200,
        "shuang_type": "",
    })()
    report = {
        "overall_score": 76,
        "llm": {
            "continuity_score": 85,
            "beat_score": 70,
            "hook_score": 65,
            "beats": {"shuang_payoff": "partial", "end_hook": "pass"},
            "chapter_suggestions": ["加强见证者三级反应"],
            "future_chapter_suggestions": ["下章换场景"],
            "hook_issue": "钩子太虚",
        },
        "warnings": [{"rule_id": "DBQ-03", "message": "章末套话"}],
    }
    system, user = build_qc_patch_prompt(
        ch, prior_content="林凡冷笑。" * 20, report=report, title="测试书",
    )
    assert "外科手术" in system
    assert "林凡冷笑" in user
    assert "加强见证者" in user
    assert "钩子太虚" in user
    assert "下章换场景" not in user
    assert "神秘人现身" in user


def test_report_actionable_for_patch_future_only_false():
    assert not report_actionable_for_patch({
        "overall_score": 90,
        "llm": {"future_chapter_suggestions": ["下章注意"]},
    })


def test_report_actionable_for_patch_with_chapter_tip():
    assert report_actionable_for_patch({
        "overall_score": 88,
        "llm": {"chapter_suggestions": ["payoff 再具体"]},
    })


def test_attach_rewrite_prompt_below_threshold():
    report = {
        "overall_score": 72,
        "llm": {
            "rewrite_prompt": "保留上章结尾，补写见证者三级反应。",
            "chapter_suggestions": ["加强 payoff"],
        },
    }
    out = attach_rewrite_prompt(report)
    assert out["rewrite_prompt"] == "保留上章结尾，补写见证者三级反应。"
    assert out["overall_score"] == 72


def test_attach_rewrite_prompt_fallback_when_llm_empty():
    report = {
        "overall_score": 65,
        "warnings": [{"rule_id": "DBQ-01", "message": "衔接弱"}],
        "llm": {
            "continuity_score": 55,
            "continuity_issue": "未承接上章钩子",
            "chapter_suggestions": ["开篇从对话切入"],
            "future_chapter_suggestions": ["下章勿重复同一打脸对象"],
        },
    }
    out = attach_rewrite_prompt(report)
    assert out["rewrite_prompt"]
    assert "衔接" in out["rewrite_prompt"]
    assert "下章" in out["rewrite_prompt"] or "后续" in out["rewrite_prompt"]


def test_attach_rewrite_prompt_clears_when_ok():
    report = {"overall_score": 85, "llm": {"rewrite_prompt": "不应保留"}}
    out = attach_rewrite_prompt(report)
    assert out["rewrite_prompt"] == ""


def test_build_lab_rewrite_prompt_includes_blockers():
    report = {
        "overall_score": 40,
        "blockers": [{"rule_id": "DLB-04", "message": "境界倒退"}],
        "llm": {"beat_issues": ["payoff 缺见证者"]},
    }
    text = build_lab_rewrite_prompt(report)
    assert "境界倒退" in text
    assert "五拍" in text
    assert REWRITE_SCORE_THRESHOLD == 80
