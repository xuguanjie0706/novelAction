"""黄金第2章质检口径与规则层误报治理。"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.dabai.lab_draft_context import LabDraftContext
from app.services.dabai.lab_qc_prompt import (
    build_lab_qc_prompt,
    golden_chapter_calibration,
)
from app.services.dabai.lab_quality import _rule_report


def _project(**kwargs):
    base = {
        "logline": "废柴逆袭",
        "title": "测试书",
        "golden_finger": {"name": "吞噬系统", "core_ability": "吞噬"},
        "power_ladder": {"levels": [{"rank": 1, "name": "引灵境"}]},
        "positioning": {},
        "benchmark": {},
        "characters": [SimpleNamespace(name="李夜", role="主角")],
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _chapter(**kwargs):
    base = {
        "chapter_number": 2,
        "title": "系统觉醒",
        "content": "李夜脑海响起冰冷提示，绑定成功。面板弹出修为点+1。",
        "location": "杂役房",
        "witnesses": ["围观弟子"],
        "expected_words": 2000,
        "realm_rank": 1,
        "shuang_type": "升级",
        "yaqu_setup": "被辱",
        "emotion_turn": "疑→证→择",
        "yinbao": "系统绑定",
        "shuang_payoff": "面板验证",
        "end_hook": "更强敌人逼近",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_golden_ch2_calibration_mentions_not_ch3_slapping():
    note = golden_chapter_calibration(_chapter(), _project())
    assert "第2章" in note
    assert "不是" in note or "非" in note


def test_build_lab_qc_prompt_includes_prev_full_and_calibration():
    ch = _chapter()
    ctx = LabDraftContext(
        prev_tail="上一章末钩",
        recent_plot_block="",
        prev_full_block="【上一章完整正文】\n" + "甲" * 500,
        prev_hook_block="【上章末钩】危机逼近",
        narrative_state_block="【全书情节时间轴】第1章…",
    )
    _, user = build_lab_qc_prompt(
        _project(), ch, ctx, plain_content=ch.content or "",
    )
    assert "黄金第2章" in user
    assert "上一章完整正文" in user
    assert "上章末钩" in user
    assert "情节时间轴" in user


def test_dlb02_overridable_on_chapter_two():
    ch = _chapter(
        witnesses=["从未出现的张三"],
        content="系统绑定成功，面板弹出。",
    )
    report = _rule_report(ch, project=_project())
    dlb02 = [w for w in report["warnings"] if w.get("rule_id") == "DLB-02"]
    assert dlb02
    assert dlb02[0].get("llm_overridable") is True
