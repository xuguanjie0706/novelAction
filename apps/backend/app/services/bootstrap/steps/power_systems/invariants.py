"""修仙多轴境界体系 — 代码级不变量校验与自动修复。"""

from __future__ import annotations

from typing import Any

_LEAP_TYPES = ("spatial", "soul", "rule", "social", "craft", "combat")


def _level_names(levels: list) -> list[str]:
    return [
        (lv.get("name") or "").strip()
        for lv in levels
        if isinstance(lv, dict) and (lv.get("name") or "").strip()
    ]


def _abilities_jaccard(a: list, b: list) -> float:
    sa = {str(x).strip() for x in (a or []) if str(x).strip()}
    sb = {str(x).strip() for x in (b or []) if str(x).strip()}
    if not sa and not sb:
        return 0.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def normalize_primary_levels(levels: list, *, min_levels: int = 7) -> list[dict]:
    """补齐 rank / leap_type / sub_levels 默认值。"""
    out: list[dict] = []
    leap_cycle = list(_LEAP_TYPES)
    for i, lv in enumerate(levels):
        if not isinstance(lv, dict):
            continue
        item = dict(lv)
        item["rank"] = item.get("rank") if isinstance(item.get("rank"), int) else (i + 1)
        if not (item.get("leap_type") or "").strip():
            item["leap_type"] = leap_cycle[i % len(leap_cycle)]
        if not item.get("sub_levels"):
            item["sub_levels"] = ["初期", "中期", "后期", "圆满"]
        if not item.get("breakthrough_trials"):
            trials = ["resource", "insight"]
            if i >= 2:
                trials.append("tribulation")
            if i >= 1:
                trials.append("heart_demon")
            item["breakthrough_trials"] = trials
        out.append(item)
    while len(out) < min_levels:
        r = len(out) + 1
        out.append({
            "rank": r,
            "name": f"第{r}境",
            "description": "待修订",
            "abilities": ["待补充"],
            "chapter_budget": 20,
            "gatekeeper": "待补充",
            "leap_type": leap_cycle[(r - 1) % len(leap_cycle)],
            "sub_levels": ["初期", "中期", "后期", "圆满"],
            "breakthrough_trials": ["resource", "insight"],
        })
    return out


def rescale_chapter_budgets(levels: list[dict], total_chapters: int) -> None:
    """将 chapter_budget 总和缩放到 [0.6, 0.8] × total_chapters。"""
    if not total_chapters or not levels:
        return
    budgets = [max(1, int(lv.get("chapter_budget") or 15)) for lv in levels]
    s = sum(budgets)
    target = int(total_chapters * 0.7)
    if s <= 0:
        per = max(1, target // len(levels))
        for lv in levels:
            lv["chapter_budget"] = per
        return
    lo, hi = int(total_chapters * 0.6), int(total_chapters * 0.8)
    if lo <= s <= hi:
        return
    scale = target / s
    for lv, b in zip(levels, budgets):
        lv["chapter_budget"] = max(1, int(b * scale))


def validate_xianxia_bundle(
    bundle: dict[str, Any],
    arch: dict[str, Any],
) -> list[str]:
    """校验 LLM 返回的修仙力量包；返回错误文案列表（空=通过）。"""
    errors: list[str] = []
    systems = bundle.get("systems")
    if not isinstance(systems, list) or len(systems) < 3:
        errors.append("systems 至少需要 3 条（主轴+道途+器物/宗门）")

    laws = bundle.get("cultivation_laws")
    if not isinstance(laws, dict) or not (laws.get("breakthrough_law") or laws.get("spirit_root_rule")):
        errors.append("cultivation_laws 须含 breakthrough_law 或 spirit_root_rule")

    if not isinstance(systems, list):
        return errors

    axes = {(s.get("axis_role") or "primary") for s in systems if isinstance(s, dict)}
    for req in arch.get("required_axes") or ["primary", "path", "artifact"]:
        if req not in axes:
            errors.append(f"缺少 axis_role={req} 的体系")

    primary = next((s for s in systems if isinstance(s, dict) and s.get("axis_role") == "primary"), None)
    if primary:
        levels = primary.get("levels") or []
        min_lv = int(arch.get("primary_min_levels") or 7)
        if len(_level_names(levels)) < min_lv:
            errors.append(f"主轴 levels 至少 {min_lv} 层")
        vols = int(arch.get("volume_count") or 0)
        start = primary.get("protagonist_start_rank")
        end = primary.get("protagonist_end_rank")
        if isinstance(start, int) and isinstance(end, int) and vols and (end - start) < vols:
            errors.append("protagonist 升级跨度应 ≥ 卷数")

        norm = [lv for lv in levels if isinstance(lv, dict)]
        leaps = [(lv.get("leap_type") or "") for lv in norm]
        for i in range(len(leaps) - 2):
            if leaps[i] and leaps[i] == leaps[i + 1] == leaps[i + 2]:
                errors.append(f"第{i + 1}~{i + 3} 层 leap_type 连续相同（注水风险）")
        for i in range(len(norm) - 1):
            if _abilities_jaccard(norm[i].get("abilities"), norm[i + 1].get("abilities")) > 0.85:
                errors.append(f"第{i + 1} 与第{i + 2} 层 abilities 过于雷同")

        total_ch = int(arch.get("total_chapters") or 0)
        if total_ch:
            s = sum(int(lv.get("chapter_budget") or 0) for lv in norm)
            lo, hi = int(total_ch * 0.6), int(total_ch * 0.8)
            if s and (s < lo or s > hi):
                errors.append(f"主轴 chapter_budget 之和 {s} 应在 [{lo},{hi}]")

    path_count = sum(1 for s in systems if isinstance(s, dict) and s.get("axis_role") == "path")
    if path_count < 1:
        errors.append("至少 1 条道途（axis_role=path）")

    return errors


def apply_auto_fixes(bundle: dict[str, Any], arch: dict[str, Any]) -> None:
    """就地修复可确定的问题（层数、章数预算、leap_type）。"""
    systems = bundle.get("systems")
    if not isinstance(systems, list):
        return
    for s in systems:
        if not isinstance(s, dict):
            continue
        if s.get("axis_role") == "primary":
            levels = s.get("levels") or []
            s["levels"] = normalize_primary_levels(
                levels,
                min_levels=int(arch.get("primary_min_levels") or 7),
            )
            rescale_chapter_budgets(s["levels"], int(arch.get("total_chapters") or 0))
    if not isinstance(bundle.get("cultivation_laws"), dict):
        bundle["cultivation_laws"] = dict(arch.get("cultivation_laws_template") or {})
