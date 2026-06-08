"""life_ledger_expand 单测。"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.bootstrap.life_ledger_expand import (
    build_life_ledger_expand_block,
    build_life_ledger_in_batch_rule,
)


def _node(sort_order: int, summary: str, title: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        id=f"n-{sort_order}",
        sort_order=sort_order,
        title=title or f"第{sort_order + 1}章",
        summary=summary,
        conflict="",
        highlight="",
        power_milestone="",
        involved_character_ids=[],
        extra={"core_event": summary},
    )


def test_in_batch_rule_always_present():
    block = build_life_ledger_expand_block(
        None,
        None,
        prior_nodes=[],
        volume_start_global=1,
        batch_start=1,
        batch_end=30,
    )
    assert "本批内自检" in block
    assert "赵管事" in block


def test_prior_death_injected_for_second_batch():
    from app.services.outline_linter.event_ledger import CharacterRef, build_timeline
    from app.services.bootstrap.life_ledger_expand import (
        _first_death_chapters,
        _rows_from_prior_nodes,
    )

    prior = [
        _node(2, "赵管事被击杀当场，萧辰夺得资源"),
    ]
    rows = _rows_from_prior_nodes(prior, volume_start_global=1, cutoff_global=14)
    refs = [CharacterRef(id="cid-zhao", name="赵管事")]
    deaths = _first_death_chapters(build_timeline(refs, rows))
    assert deaths
    assert deaths[0][0] == "赵管事"
    assert deaths[0][1] == 3

    block = build_life_ledger_expand_block(
        None,
        None,
        prior_nodes=prior,
        volume_start_global=1,
        batch_start=16,
        batch_end=30,
    )
    assert "本批内自检" in block


def test_in_batch_rule_standalone():
    text = build_life_ledger_in_batch_rule(batch_start=1, batch_end=30)
    assert "involved_characters" in text


# ── 生成后：本批内死而复死确定性检测 ────────────────────────────────────────

def _chars():
    from app.services.outline_linter.event_ledger import CharacterRef

    return [CharacterRef(id="ye", name="叶辰")]


def test_intra_batch_detects_death_twice():
    """同批内：第2章死、第5章再被杀 → 检出（前置账本无法覆盖的同窗口场景）。"""
    from app.services.bootstrap.life_ledger_expand import (
        build_life_violation_hint,
        detect_intra_batch_life_violations,
    )

    batch = [
        {"title": "第1章", "core_event": "叶辰登场修炼"},
        {"title": "第2章", "core_event": "叶辰被一掌击杀，当场身亡"},
        {"title": "第3章", "core_event": "众人议论"},
        {"title": "第4章", "core_event": "穆清风出手"},
        {"title": "第5章", "core_event": "穆清风一剑斩杀叶辰，复仇成功"},
    ]
    violations = detect_intra_batch_life_violations(
        batch, batch_start=1, char_refs=_chars(), dead_before={}, volume_start_global=1,
    )
    assert violations
    name, first_death, rekill, _ = violations[0]
    assert name == "叶辰"
    assert first_death == 2 and rekill == 5
    hint = build_life_violation_hint(violations)
    assert "叶辰" in hint and "第2章" in hint and "第5章" in hint


def test_intra_batch_respects_revive_no_violation():
    """第2章死、第4章诈死复活、第5章再死 → 复活后再死不算硬伤。"""
    from app.services.bootstrap.life_ledger_expand import (
        detect_intra_batch_life_violations,
    )

    batch = [
        {"title": "第1章", "core_event": "叶辰登场"},
        {"title": "第2章", "core_event": "叶辰被一掌击杀"},
        {"title": "第3章", "core_event": "平静"},
        {"title": "第4章", "core_event": "原来叶辰假死，借尸还魂归来"},
        {"title": "第5章", "core_event": "穆清风终于斩杀叶辰"},
    ]
    violations = detect_intra_batch_life_violations(
        batch, batch_start=1, char_refs=_chars(), dead_before={}, volume_start_global=1,
    )
    assert not violations


def test_intra_batch_uses_dead_before_from_prior_window():
    """前一窗口已死（dead_before），本窗口再杀 → 检出（跨窗口确定性兜底）。"""
    from app.services.bootstrap.life_ledger_expand import (
        detect_intra_batch_life_violations,
    )

    batch = [
        {"title": "第11章", "core_event": "穆清风当场格杀叶辰"},
    ]
    violations = detect_intra_batch_life_violations(
        batch,
        batch_start=11,
        char_refs=_chars(),
        dead_before={"ye": ("叶辰", 2)},
        volume_start_global=1,
    )
    assert violations
    assert violations[0][1] == 2 and violations[0][2] == 11


def test_build_life_violation_hint_empty():
    from app.services.bootstrap.life_ledger_expand import build_life_violation_hint

    assert build_life_violation_hint([]) == ""


def test_intra_batch_uses_declared_fields_when_prose_silent():
    """结构化声明：正文无杀戮动词，仅靠 item['deaths'] 也能检出死而复死。"""
    from app.services.bootstrap.life_ledger_expand import (
        detect_intra_batch_life_violations,
    )

    batch = [
        {"title": "第1章", "core_event": "叶辰登场"},
        {"title": "第2章", "core_event": "叶辰倒在血泊里再没起来", "deaths": ["叶辰"]},
        {"title": "第3章", "core_event": "余波"},
        {"title": "第4章", "core_event": "新的对手登场", "deaths": ["叶辰"]},
    ]
    violations = detect_intra_batch_life_violations(
        batch, batch_start=1, char_refs=_chars(), dead_before={}, volume_start_global=1,
    )
    assert violations
    assert violations[0][1] == 2 and violations[0][2] == 4


def test_intra_batch_declared_revive_clears():
    """声明复活：deaths→revives→deaths 不算硬伤。"""
    from app.services.bootstrap.life_ledger_expand import (
        detect_intra_batch_life_violations,
    )

    batch = [
        {"title": "第1章", "core_event": "x", "deaths": ["叶辰"]},
        {"title": "第2章", "core_event": "y", "revives": ["叶辰"]},
        {"title": "第3章", "core_event": "z", "deaths": ["叶辰"]},
    ]
    violations = detect_intra_batch_life_violations(
        batch, batch_start=1, char_refs=_chars(), dead_before={}, volume_start_global=1,
    )
    assert not violations


def test_build_chapter_extra_persists_declared_fields():
    """章纲 extra 落库结构化生死声明，且规整空白/空串。"""
    from app.services.bootstrap.steps.chapter_extra import build_chapter_extra

    extra = build_chapter_extra(
        {"title": "第1章", "deaths": ["叶辰", " ", ""], "revives": ["苏云"]},
        is_fanqie=False,
    )
    assert extra["deaths_declared"] == ["叶辰"]
    assert extra["revives_declared"] == ["苏云"]
    # 无声明时为空数组
    assert build_chapter_extra({"title": "第2章"}, is_fanqie=False)["deaths_declared"] == []
