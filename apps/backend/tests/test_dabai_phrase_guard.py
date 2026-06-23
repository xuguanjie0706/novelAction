"""lab_phrase_guard + 分场见证者指令 + 自然度质检合并。"""
from types import SimpleNamespace
from uuid import uuid4

from app.services.dabai.lab_phrase_guard import (
    collect_banned_phrases,
    format_witness_reaction_instruction,
    scan_cliche_fragments,
    witness_reaction_mode_index,
    witness_reaction_mode_label,
)
from app.services.dabai.lab_scene_plan import format_scene_block
from app.services.dabai.prose.prompt_assemble import build_prose_prompt
from app.services.dabai.qc_merge import _merge_report


def test_witness_mode_rotates_by_chapter():
    assert witness_reaction_mode_index(1) == 1
    assert witness_reaction_mode_index(2) == 2
    assert witness_reaction_mode_index(5) == 1
    assert "②" in witness_reaction_mode_label(2)


def test_format_scene_block_no_hardcoded_ladder():
    block = format_scene_block({
        "scenes": [{"name": "试", "location": "外", "word_budget": 600, "event": "压"}],
        "opening_line": "冲突入场",
    }, chapter_number=3)
    assert "愣住→不信→震惊→心服" not in block
    assert "③" in block or "见证者反应" in block


def test_format_scene_block_per_witness_reactions():
    block = format_scene_block({
        "scenes": [{"name": "试", "location": "外", "word_budget": 600}],
        "witness_reactions": [
            {"name": "甲", "mode": 2, "beats": ["捂嘴", "铁钩落地"]},
        ],
    }, chapter_number=5)
    assert "甲" in block
    assert "捂嘴" in block


def test_scan_cliche_fragments():
    text = "阴寒灵力轰然倒灌，万魂幡微微颤动，他不敢置信。"
    hits = scan_cliche_fragments(text)
    assert "阴寒灵力" in hits
    assert "不敢置信" in hits


def test_collect_banned_phrases_empty_for_ch1():
    """第 1 章无前文，禁词列表为空。"""
    class _Q:
        def filter(self, *a, **k):
            return self
        def order_by(self, *a):
            return self
        def all(self):
            return []

    class _Db:
        def query(self, *a):
            return _Q()

    assert collect_banned_phrases(_Db(), uuid4(), 1) == []


def test_prose_prompt_includes_phrase_guard_and_witness_hint():
    project = SimpleNamespace(
        title="测试书",
        logline="测试",
        golden_finger={"name": "幡", "core_ability": "收魂"},
        power_ladder={"levels": [{"name": "炼气"}]},
        characters=[SimpleNamespace(name="主角", role="主角")],
        positioning={},
        benchmark={},
    )
    ch = SimpleNamespace(
        chapter_number=4,
        title="试",
        yaqu_setup="压",
        emotion_turn="扳",
        yinbao="爆",
        shuang_payoff="爽",
        end_hook="钩",
        shuang_type="打脸",
        location="外",
        witnesses=["甲"],
        realm_rank=1,
        is_big_beat=False,
        expected_words=2000,
        involved_characters=[],
    )
    system, user = build_prose_prompt(
        project, ch,
        phrase_guard_block="【近章已用表达 · 本章禁用复述】\n  - 不敢置信",
    )
    assert "见证者与自然度" in system
    assert "近章已用表达" in user


def test_merge_report_naturalness_weight():
    rule = {"blockers": [], "warnings": []}
    llm = {
        "continuity_score": 90,
        "hook_score": 90,
        "beats": {k: "pass" for k in ("yaqu", "trigger", "yinbao", "payoff", "hook")},
        "naturalness_score": 60,
        "overused_phrases": ["不敢置信"],
        "witness_reaction_issue": "王铁柱重复震惊",
    }
    rep = _merge_report(rule, llm, "ok")
    assert rep["overall_score"] < 90
    assert any(w.get("rule_id") == "DBQ-07" for w in rep.get("warnings") or [])
