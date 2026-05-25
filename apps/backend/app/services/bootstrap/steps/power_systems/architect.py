"""修仙多轴力量架构决策（规则 + positioning，无额外 LLM）。"""

from __future__ import annotations

from typing import Any

from app.services.genre_kit import get_genre_kit, normalize_genre

_MULTI_AXIS_GENRES = frozenset({"仙侠", "玄幻"})


def uses_multi_axis_power(genre: str | None) -> bool:
    """是否启用修仙五轴生成（当前：仙侠 / 玄幻）。"""
    return normalize_genre(genre) in _MULTI_AXIS_GENRES


def build_power_architecture(ctx: dict) -> dict[str, Any]:
    """
    从 genre_kit + positioning 推导本书力量架构蓝图。

    @returns cultivation_laws 草案、paths_pick、required_axes 等
    """
    genre = normalize_genre(ctx.get("genre") or ctx.get("project_genre"))
    kit = get_genre_kit(genre)
    defaults = dict(kit.get("power_architecture_defaults") or {})
    positioning = ctx.get("positioning") or {}
    tropes = positioning.get("tropes") or positioning.get("satisfaction_tropes") or []
    trope_str = " ".join(tropes) if isinstance(tropes, list) else str(tropes)

    paths_pool = list(defaults.get("paths_pool") or ["sword", "pill", "body"])
    paths_pick = int(defaults.get("paths_pick") or 2)
    if "丹" in trope_str or "炼丹" in trope_str:
        paths_pick = max(paths_pick, 2)
        if "pill" not in paths_pool[:paths_pick]:
            paths_pool = ["pill"] + [p for p in paths_pool if p != "pill"]

    path_labels = {
        "sword": "剑修·剑意",
        "pill": "丹修·丹火",
        "body": "体修·肉身",
        "talisman": "符修·符阶",
        "array": "阵修·阵盘",
        "demon": "魔修·魔种",
    }
    selected_paths = paths_pool[:paths_pick]

    total_chapters = int(ctx.get("chapter_quota_total") or 0)
    volume_count = int(ctx.get("chapter_quota_total_volumes") or 0)
    if not total_chapters and ctx.get("target_words"):
        from app.services.outline_planning import words_to_plan

        plan = words_to_plan(int(ctx["target_words"]))
        total_chapters = plan.get("total_chapters", 300)
        volume_count = plan.get("total_volumes", 10)

    return {
        "genre": genre,
        "multi_axis": uses_multi_axis_power(genre),
        "required_axes": list(defaults.get("required_axes") or ["primary", "path", "artifact"]),
        "optional_axes": list(defaults.get("optional_axes") or ["sect", "dao_heart"]),
        "primary_min_levels": int(defaults.get("primary_min_levels") or 7),
        "selected_paths": selected_paths,
        "path_labels": {p: path_labels.get(p, p) for p in selected_paths},
        "artifact_tier_names": list(
            defaults.get("artifact_tier_names")
            or ["凡品", "灵器", "宝器", "灵宝", "古宝", "道器", "仙器"]
        ),
        "sect_rank_names": list(
            defaults.get("sect_rank_names")
            or ["外门弟子", "内门弟子", "真传弟子", "执事", "长老", "副掌门", "掌门", "老祖"]
        ),
        "total_chapters": total_chapters,
        "volume_count": volume_count,
        "cultivation_laws_template": {
            "spirit_root_rule": "灵根决定修炼速度；杂灵根可融法但突破更难",
            "breakthrough_law": "金丹及以上须渡天劫；魔修可避劫但积孽招反噬",
            "ascension_rule": "一界飞升名额有限，大宗垄断高阶灵脉",
            "golden_finger_cost": "金手指每次动用消耗寿元或加深心魔",
        },
    }
