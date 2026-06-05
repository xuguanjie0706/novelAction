"""番茄主轴境界策略单测。"""
from app.services.bootstrap.fanqie_realm_policy import (
    hydrate_fanqie_power_ctx,
    normalize_realm_label_for_primary_axis,
)


def test_hydrate_fanqie_power_ctx_sets_one_based_ranks():
    ctx = {
        "power_ladder": {
            "social_ladder": [
                {"tier": 1, "name": "边陲小城弃民"},
                {"tier": 2, "name": "帝国宗门天骄"},
            ],
            "protagonist_start_tier": 1,
            "protagonist_end_tier": 2,
        },
    }
    hydrate_fanqie_power_ctx(ctx)
    assert ctx["power_level_names"] == ["边陲小城弃民", "帝国宗门天骄"]
    assert ctx["power_level_registry"]["边陲小城弃民"]["rank"] == 1


def test_normalize_rejects_cultivation_term():
    name_to_rank = {"边陲小城弃民": 1, "帝国宗门天骄": 2}
    label, warn = normalize_realm_label_for_primary_axis("筑基期（经脉重塑）", name_to_rank)
    assert label == "边陲小城弃民"
    assert warn and "筑基" in warn


def test_normalize_substage_keeps_ladder_prefix():
    name_to_rank = {"边陲小城弃民": 1, "帝国宗门天骄": 2}
    label, _ = normalize_realm_label_for_primary_axis("边陲小城弃民初期", name_to_rank)
    assert label == "边陲小城弃民"
