"""Bootstrap Step 0：立项会议（题材定位）— 单次调用版。

一次 LLM 调用同时完成三项任务：
  ① 生成 3 个互竞定位方案（conservative / differentiated / niche）
  ② 读者模拟器对每个方案 hook_text 打分（reader_score / reader_reason）
  ③ 横向对比后自动择优（auto_selection.selected_index + comparison）

返回结构（backward-compat）：
  {
    # 选中方案的扁平字段（与旧版 ctx['positioning'] 契约一致）
    "target_audience": ..., "tropes": [...], ...
    # 新增多候选元数据
    "candidates":              [...],  # 每项含 reader_score 等扩展字段
    "auto_selected_index":     int,
    "auto_selection_reason":   str,
    "auto_selection_comparison": str,
  }
"""

from __future__ import annotations

import logging
from typing import Any

from app.schemas.bootstrap_positioning import (
    detect_trope_conflicts,
    try_validate_candidate,
    try_validate_positioning,
)
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts.positioning import (
    UNIFIED_SYSTEM,
    build_unified_prompt,
)

logger = logging.getLogger(__name__)


async def _call_once(svc: Any, ctx: dict) -> dict | None:
    """单次调用：生成候选 + 读者评分 + 择优，返回解析后的 dict 或 None。

    最多重试 3 次（schema 校验失败时附加修正提示）。

    Returns:
        含 candidates[] 和 auto_selection{} 的解析结果，或 None（全部失败）。
    """
    last_err = ""
    for attempt in range(3):
        fix_block = (
            f"\n\n【第{attempt+1}次重试：上次输出未通过校验，请修正后仅返回 JSON】\n"
            f"错误：{last_err}\n"
            "必须满足：candidates 数组有 3 条、每条含所有必填字段、"
            "三条 positioning_type 各不相同、reader_score 为 1-10 整数、"
            "auto_selection.selected_index 为 0/1/2。"
            if last_err else ""
        )
        prompt = build_unified_prompt(ctx) + fix_block
        try:
            raw = await svc._call_with_retry(
                UNIFIED_SYSTEM, prompt, max_tokens=4096, task="bootstrap.positioning",
            )
            data = parse_json(raw)
        except Exception as exc:
            last_err = f"JSON 解析失败：{exc}"
            logger.warning("_call_once attempt %d: %s", attempt + 1, last_err)
            continue

        if not isinstance(data, dict):
            last_err = "根类型必须为 JSON 对象"
            continue

        cands_raw = data.get("candidates")
        if not isinstance(cands_raw, list) or len(cands_raw) < 2:
            last_err = f"candidates 为空或少于2条（得到 {type(cands_raw).__name__}）"
            continue

        # 校验每个候选（宽松：至少有1条通过即可继续）
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
            last_err = f"全部 {len(cands_raw)} 个候选均未通过 schema 校验"
            continue

        # auto_selection（容错：字段缺失时用默认值）
        sel_raw = data.get("auto_selection") or {}
        if not isinstance(sel_raw, dict):
            sel_raw = {}
        data["candidates"] = validated
        data["auto_selection"] = sel_raw
        return data

    logger.error("_call_once failed after 3 attempts; last_err=%s", last_err)
    return None


async def gen_positioning(svc: Any, ctx: dict) -> dict:
    """立项会议主入口：单次调用完成3候选+评分+择优。

    返回向后兼容的扁平 positioning dict（选中方案字段在顶层）
    + candidates / auto_selected_index / auto_selection_reason / auto_selection_comparison。

    失败时返回空 dict（调用方检查 ``if not positioning``）。
    """
    result = await _call_once(svc, ctx)
    if not result:
        return {}

    candidates: list[dict] = result["candidates"]
    sel_raw: dict = result.get("auto_selection") or {}

    # 解析 selected_index，兜底为 0
    sel_idx = sel_raw.get("selected_index")
    if not isinstance(sel_idx, int) or not (0 <= sel_idx < len(candidates)):
        sel_idx = 0

    selected = candidates[sel_idx]

    # 用基础 BootstrapPositioning 校验选中方案的扁平字段
    normalized, err = try_validate_positioning(selected)
    if normalized is None:
        # 尝试其他候选兜底
        for alt_idx, cand in enumerate(candidates):
            normalized, err = try_validate_positioning(cand)
            if normalized:
                sel_idx = alt_idx
                selected = cand
                break
    if normalized is None:
        logger.error("gen_positioning: all candidates failed base validation; err=%s", err)
        return {}

    # 合并：扁平字段（来自 normalized）+ 候选元数据
    normalized["candidates"] = candidates
    normalized["auto_selected_index"] = sel_idx
    normalized["auto_selection_reason"] = str(sel_raw.get("recommended_reason") or "")[:300]
    normalized["auto_selection_comparison"] = str(sel_raw.get("comparison") or "")[:500]

    return normalized
