"""Bootstrap Step 0：立项会议（题材定位）— 单次调用版。

一次 LLM 调用同时完成三项任务：
  ① 生成 3 个互竞定位方案（conservative / differentiated / niche）
  ② 读者模拟器对每个方案 hook_text 打分（reader_score / reader_reason）
  ③ 横向对比后自动择优（auto_selection.selected_index + comparison）
"""
from __future__ import annotations

import logging
from typing import Any

from app.schemas.bootstrap_positioning import (
    detect_trope_conflicts,
    try_validate_candidate,
    try_validate_positioning,
)
from app.services.bootstrap.json_once import BootstrapStepError, call_bootstrap_json_once
from app.services.bootstrap.prompts.positioning import (
    UNIFIED_SYSTEM,
    build_unified_prompt,
)

logger = logging.getLogger(__name__)

_STEP = "positioning"


def _validate_unified_response(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "根类型必须为 JSON 对象"

    cands_raw = data.get("candidates")
    if not isinstance(cands_raw, list) or len(cands_raw) < 2:
        return f"candidates 为空或少于2条（得到 {type(cands_raw).__name__}）"

    validated: list[dict] = []
    for item in cands_raw:
        if not isinstance(item, dict):
            continue
        norm, _ = try_validate_candidate(item)
        if norm is not None:
            conflicts = detect_trope_conflicts(norm.get("tropes") or [])
            if conflicts:
                logger.warning("Trope conflicts in candidate %d: %s", len(validated), conflicts)
                norm["_trope_conflicts"] = conflicts
            validated.append(norm)

    if not validated:
        return f"全部 {len(cands_raw)} 个候选均未通过 schema 校验"

    sel_raw = data.get("auto_selection") or {}
    if not isinstance(sel_raw, dict):
        sel_raw = {}
    data["candidates"] = validated
    data["auto_selection"] = sel_raw
    return None


async def _call_once(svc: Any, ctx: dict) -> dict:
    """单次调用：生成候选 + 读者评分 + 择优。

    @raises BootstrapStepError: JSON 解析或 schema 校验失败（不重试）
    """
    prompt = build_unified_prompt(ctx)
    data = await call_bootstrap_json_once(
        svc,
        step=_STEP,
        system=UNIFIED_SYSTEM,
        prompt=prompt,
        task="bootstrap.positioning",
        validate=_validate_unified_response,
    )
    return data


async def gen_positioning(svc: Any, ctx: dict) -> dict:
    """立项会议主入口：单次 LLM + 择优，失败即 ``BootstrapStepError``。"""
    result = await _call_once(svc, ctx)

    candidates: list[dict] = result["candidates"]
    sel_raw: dict = result.get("auto_selection") or {}

    sel_idx = sel_raw.get("selected_index")
    if not isinstance(sel_idx, int) or not (0 <= sel_idx < len(candidates)):
        sel_idx = 0

    selected = candidates[sel_idx]

    normalized, err = try_validate_positioning(selected)
    if normalized is None:
        for alt_idx, cand in enumerate(candidates):
            normalized, err = try_validate_positioning(cand)
            if normalized:
                sel_idx = alt_idx
                selected = cand
                break

    if normalized is None:
        raise BootstrapStepError(
            _STEP,
            f"全部候选未通过立项校验：{err or '未知原因'}",
        )

    normalized["candidates"] = candidates
    normalized["auto_selected_index"] = sel_idx
    normalized["auto_selection_reason"] = str(sel_raw.get("recommended_reason") or "")[:300]
    normalized["auto_selection_comparison"] = str(sel_raw.get("comparison") or "")[:500]

    return normalized
