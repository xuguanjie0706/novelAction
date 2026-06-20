"""分场/正文字数预算：章纲 expected_words → 分场 word_budget → 正文篇幅上限。

设计动机：LLM 分场常把各场 budget 加总到 3000+，正文 prompt 仍按章纲 ±200，
导致「章纲 2200、正文 3000+」。本模块在分场落库前强制归一化，正文只认分场合计。
"""
from __future__ import annotations

from typing import Any

from app.models.dabai import DabaiChapterOutline

_MIN_SCENE_BUDGET = 120


def chapter_word_target(ch: DabaiChapterOutline) -> int:
    """章纲目标字数（正文/分场归一化基准）。"""
    return max(800, int(ch.expected_words or 2000))


def dabai_draft_max_tokens(word_hi: int) -> int:
    """dabai 正文 completion 预算：对齐正文 prompt 硬上限（分场合计或章纲 hi），防失控超长。"""
    from app.services.llm_token_budgets import ensure_min_completion_tokens

    hi = max(1200, int(word_hi or 2200))
    cap = max(1200, int(hi * 1.06))
    return min(ensure_min_completion_tokens(cap), 4096)


def _coerce_budget(scene: dict) -> int:
    try:
        return max(0, int(scene.get("word_budget") or 0))
    except (TypeError, ValueError):
        return 0


def _even_split(n: int, chapter_target: int) -> list[int]:
    """无 LLM budget 时按场数均分（末场吃掉余数）。"""
    n = max(1, n)
    base = chapter_target // n
    budgets = [max(_MIN_SCENE_BUDGET, base) for _ in range(n)]
    drift = chapter_target - sum(budgets)
    budgets[-1] = max(_MIN_SCENE_BUDGET, budgets[-1] + drift)
    return budgets


def normalize_scene_word_budgets(
    scenes: list[dict],
    chapter_target: int,
) -> list[dict]:
    """将各场 word_budget 缩放/补齐，使合计 **严格等于** chapter_target。"""
    chapter_target = max(800, int(chapter_target))
    valid = [dict(s) for s in scenes if isinstance(s, dict)]
    if not valid:
        return []

    raw = [_coerce_budget(s) for s in valid]
    total = sum(raw)
    if total <= 0:
        scaled = _even_split(len(valid), chapter_target)
    else:
        scaled = [
            max(_MIN_SCENE_BUDGET, round(b * chapter_target / total))
            for b in raw
        ]
        drift = chapter_target - sum(scaled)
        scaled[-1] = max(_MIN_SCENE_BUDGET, scaled[-1] + drift)

    for sc, budget in zip(valid, scaled):
        sc["word_budget"] = budget
    return valid


def finalize_scene_plan_result(
    result: dict,
    ch: DabaiChapterOutline,
) -> dict:
    """分场 JSON 落库/注入正文前：预算归一化到章纲目标。"""
    out = dict(result)
    target = chapter_word_target(ch)
    scenes = normalize_scene_word_budgets(out.get("scenes") or [], target)
    out["scenes"] = scenes
    out["word_budget_total"] = sum(_coerce_budget(s) for s in scenes)
    return out


def resolve_prose_word_bounds(
    scene_plan: dict | None,
    ch: DabaiChapterOutline | None = None,
) -> tuple[int, int, int] | None:
    """有分场时返回 (target, lo, hi)；正文篇幅只认分场合计，区间偏紧防爆表。"""
    if not scene_plan:
        return None
    scenes = [s for s in (scene_plan.get("scenes") or []) if isinstance(s, dict)]
    if not scenes:
        return None
    total = sum(_coerce_budget(s) for s in scenes)
    if total <= 0 and ch is not None:
        total = chapter_word_target(ch)
    if total <= 0:
        return None
    lo = max(800, total - max(50, int(total * 0.04)))
    hi = min(total + 50, int(total * 1.05))
    return total, lo, hi


def format_per_scene_budget_lines(scenes: list[dict]) -> str:
    """正文任务：逐场上限（预算 ±5% 或 ±30 字，取较小裕量）。"""
    lines: list[str] = []
    for i, sc in enumerate(scenes[:5], 1):
        if not isinstance(sc, dict):
            continue
        b = _coerce_budget(sc)
        if b <= 0:
            continue
        margin = min(30, max(15, int(b * 0.05)))
        lo_s = max(80, b - margin)
        hi_s = b + margin
        name = str(sc.get("name") or f"场{i}")
        lines.append(f"  场{i}「{name}」{lo_s}～{hi_s} 字（预算 {b}，不得超过 {hi_s}）")
    return "\n".join(lines)


def scene_plan_from_row(
    opening_line: str | None,
    scenes: Any,
    ch: DabaiChapterOutline,
) -> dict | None:
    """从 DB 行重建分场 dict 并重新归一化（章纲改字数后仍对齐）。"""
    if not isinstance(scenes, list) or not scenes:
        return None
    return finalize_scene_plan_result(
        {"opening_line": opening_line or "", "scenes": scenes},
        ch,
    )
