"""每步生成函数：组装 prompt → 调 LLM/mock → parse → normalize → validate（带 1 次重试）。

每个 run_step 是无状态自由函数，输入累积 ctx，输出该步产物（dict 或 list）。
章纲步在调用前把目标卷塞进 ctx['_target_volume']。
"""

from __future__ import annotations

import logging
from typing import Any

from dabai import prompts, schemas
from dabai.config import DabaiConfig
from dabai.llm_client import DabaiLLM, LLMError

logger = logging.getLogger("dabai.steps")


def run_step(step: str, ctx: dict, llm: DabaiLLM, cfg: DabaiConfig) -> Any:
    """执行单步并返回归一化后的产物。失败重试 1 次，仍失败则抛 LLMError。"""
    system, user = prompts.build(step, ctx, cfg)
    last_err = ""
    for attempt in range(2):
        try:
            raw = llm.generate_json(step, system, user)
        except LLMError as exc:
            last_err = str(exc)
            logger.warning("%s 调用失败(attempt=%d)：%s", step, attempt + 1, exc)
            continue
        data = schemas.normalize_step(step, raw)
        errors = schemas.validate_step(step, data)
        if not errors:
            return data
        last_err = "；".join(errors[:5])
        logger.warning("%s 校验未过(attempt=%d)：%s", step, attempt + 1, last_err)
        # 重试时把校验问题回灌到 prompt 末尾
        user = user + f"\n\n上次输出有问题，请修正后重新返回完整 JSON：{last_err}"
    raise LLMError(f"{step} 连续 2 次失败：{last_err}")


def run_chapter_outlines(ctx: dict, llm: DabaiLLM, cfg: DabaiConfig) -> list[dict]:
    """章纲步特化入口：选定目标卷（默认第 1 卷）后调用 run_step。

    懒展开理念：默认只展开 first volume；可由 cfg.first_volume_only 控制。
    """
    vols = ctx.get("volumes") or []
    if not vols:
        raise LLMError("章纲步缺少卷骨架（volumes 为空）")
    target = vols[0]
    ctx["_target_volume"] = target
    chapters = run_step("chapter_outlines", ctx, llm, cfg)
    # 截断/对齐到计划章数
    n = int(target.get("planned_chapters", cfg.volume_chapters))
    if len(chapters) > n:
        chapters = chapters[:n]
    # 章号重排，保证连续
    for i, ch in enumerate(chapters):
        ch["chapter_number"] = i + 1
    ctx.pop("_target_volume", None)
    return chapters
