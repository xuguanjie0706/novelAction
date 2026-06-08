"""chapter_plan_postcheck 单测。"""
from app.services.bootstrap.chapter_plan_postcheck import (
    build_batch_postcheck_retry_hint,
    build_choice_cost_violation_hint,
    detect_empty_choice_costs,
)


def test_detect_empty_choice_costs_by_index():
    batch = [
        {"choice_cost": "失去左臂，血流不止"},
        {"choice_cost": ""},
        {"choice_cost": "无"},
    ]
    assert detect_empty_choice_costs(batch, batch_start=11) == [12, 13]


def test_detect_empty_choice_costs_respects_chapter_number():
    batch = [
        {"chapter_number": 5, "choice_cost": "经脉灼裂"},
        {"chapter_number": 6, "choice_cost": ""},
    ]
    assert detect_empty_choice_costs(batch, batch_start=1) == [6]


def test_build_choice_cost_violation_hint_lists_chapters():
    hint = build_choice_cost_violation_hint([16, 11, 12])
    assert "第 11、12、16 章" in hint
    assert "choice_cost" in hint


def test_build_batch_postcheck_retry_hint_combines_life_and_cost():
    from app.services.outline_linter.event_ledger import CharacterRef

    batch = [
        {
            "chapter_number": 3,
            "title": "再斩叶辰",
            "core_event": "叶辰被击杀",
            "choice_cost": "暴露行踪引来追兵",
            "deaths": ["叶辰"],
        },
        {"chapter_number": 4, "title": "又杀叶辰", "core_event": "叶辰被格杀", "choice_cost": ""},
    ]
    refs = [CharacterRef(id="ye", name="叶辰")]
    hint, life_v, gaps = build_batch_postcheck_retry_hint(
        batch,
        batch_start=3,
        char_refs=refs,
        dead_before={},
        volume_start_global=1,
    )
    assert life_v
    assert gaps == [4]
    assert "死而复死" in hint
    assert "choice_cost" in hint
