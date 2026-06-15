"""lab_chapter_boundary — 后续章边界与跨章角色保护。"""
from __future__ import annotations

from app.services.dabai.lab_chapter_boundary import (
    check_future_cast_violations,
    death_hit_for_name,
    lint_outline_future_cast_conflict,
)
from app.services.dabai.lab_realm_baseline import _sync_sub_rank_fields
from types import SimpleNamespace


def test_death_hit_for_protected_name():
    text = "赵猛连惨叫都没发全，就被三块铁片贯穿胸口，没了声息。"
    assert death_hit_for_name(text, "赵猛") is not None


def test_death_hit_miss_when_alive():
    text = "赵猛被震飞吐血，倒在地上哀嚎不止。"
    assert death_hit_for_name(text, "赵猛") is None


def test_check_future_cast_violations_blocker():
    content = "赵猛被贯穿胸口，当场没了声息。"
    hits = check_future_cast_violations(content, ["赵猛"])
    assert len(hits) == 1
    assert hits[0]["rule_id"] == "DLB-05"


def test_lint_outline_future_cast_conflict():
    chapters = [
        {
            "chapter_number": 3,
            "involved_characters": ["沈砚", "赵猛"],
            "yinbao": "沈砚震杀赵猛",
            "shuang_payoff": "",
            "end_hook": "",
            "yaqu_setup": "",
        },
        {
            "chapter_number": 4,
            "involved_characters": ["沈砚", "赵猛", "林德"],
        },
    ]
    issues = lint_outline_future_cast_conflict(chapters)
    assert issues
    assert issues[0][0] == 3


def test_sync_sub_rank_fields_from_integer():
    project = SimpleNamespace(power_ladder={"levels": [{"rank": 1, "name": "炼气境"}]})
    fact = {"realm": "炼气境", "realm_sub_rank": 2}
    out = _sync_sub_rank_fields(fact, project)
    assert out["realm_sub_rank"] == 2
    assert "第2层" in out["realm"]
