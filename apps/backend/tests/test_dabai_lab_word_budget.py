"""分场/正文字数预算归一化。"""
from app.services.dabai.lab_word_budget import (
    finalize_scene_plan_result,
    normalize_scene_word_budgets,
    resolve_prose_word_bounds,
)


class _Ch:
    expected_words = 2200


def test_normalize_scales_overshoot_to_chapter_target():
    scenes = [
        {"name": "a", "word_budget": 900},
        {"name": "b", "word_budget": 1100},
        {"name": "c", "word_budget": 1200},
    ]
    out = normalize_scene_word_budgets(scenes, 2200)
    assert sum(s["word_budget"] for s in out) == 2200


def test_finalize_scene_plan_result_sets_total():
    result = finalize_scene_plan_result(
        {"scenes": [{"word_budget": 1000}, {"word_budget": 1500}]},
        _Ch(),
    )
    assert result["word_budget_total"] == 2200


def test_prose_bounds_tight_hi():
    plan = {"scenes": [{"word_budget": 700}, {"word_budget": 1500}]}
    target, lo, hi = resolve_prose_word_bounds(plan, _Ch())
    assert target == 2200
    assert hi <= 2200 + 50
    assert hi <= int(2200 * 1.05)
    assert lo >= 2200 - 100
