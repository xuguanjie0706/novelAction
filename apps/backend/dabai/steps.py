"""每步生成函数（异步）：组装 prompt → await call() → normalize → validate（重试1次）。

`call` 是注入的异步调用器，签名 `async (step, system, user, meta) -> 已解析JSON`：
  - 真实 web 路径注入 AIService._call_ai 封装（继承计费/日志/采样）；
  - mock / CLI 注入 DabaiLLM 封装。
章纲步支持分批（每批一次 call），批间用上一批结尾硬承接。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Awaitable, Callable

from dabai import prompts, schemas
from dabai.config import DabaiConfig

logger = logging.getLogger("dabai.steps")

# 注入式异步调用器类型
CallFn = Callable[[str, str, str, dict | None], Awaitable[Any]]


class DabaiStepError(RuntimeError):
    """步骤生成/校验失败。"""


async def run_step(
    step: str, ctx: dict, call: CallFn, cfg: DabaiConfig, meta: dict | None = None,
) -> Any:
    """执行单步并返回归一化后的产物。失败重试 1 次，仍失败则抛 DabaiStepError。"""
    system, user = prompts.build(step, ctx, cfg)
    last_err = ""
    for attempt in range(2):
        try:
            raw = await call(step, system, user, meta)
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            logger.warning("%s 调用失败(attempt=%d)：%s", step, attempt + 1, exc)
            continue
        data = schemas.normalize_step(step, raw)
        errors = schemas.validate_step(step, data)
        if not errors:
            return data
        last_err = "；".join(errors[:5])
        logger.warning("%s 校验未过(attempt=%d)：%s", step, attempt + 1, last_err)
        user = user + f"\n\n上次输出有问题，请修正后重新返回完整 JSON：{last_err}"
    raise DabaiStepError(f"{step} 连续 2 次失败：{last_err}")


def _batch_ranges(planned: int, size: int) -> list[tuple[int, int]]:
    """切分章节区间，如 (60,30) → [(1,30),(31,60)]。"""
    size = max(5, size)
    return [(s, min(s + size - 1, planned)) for s in range(1, planned + 1, size)]


def _tail_of(batch: list[dict]) -> str:
    if not batch:
        return ""
    last = batch[-1]
    return (last.get("end_hook") or last.get("shuang_payoff") or "").strip()


def _realm_max(ctx: dict) -> int | None:
    levels = (ctx.get("power_ladder") or {}).get("levels") or []
    ranks = [int(l.get("rank", 0)) for l in levels if str(l.get("rank", "")).strip()]
    return max(ranks) if ranks else None


def _enforce_realm(batch: list[dict], running: int, vr_hi: int | None, rmax: int | None) -> int:
    """境界脊柱硬保证：本批每章 realm_rank 单调不减、不超卷末/体系上限。

    模型若回退或漏填，直接拉到当前档（写库数据永不回退）。返回更新后的 running。
    """
    cap = min([x for x in (vr_hi, rmax) if x] or [10 ** 9])
    for ch in batch:
        rr = ch.get("realm_rank")
        rr = rr if isinstance(rr, int) and rr >= running else running
        rr = min(rr, cap)
        ch["realm_rank"] = rr
        running = rr
    return running


async def aiter_chapter_batches(
    ctx: dict, call: CallFn, cfg: DabaiConfig, target_volume: dict,
) -> AsyncIterator[tuple[list[dict], int, int]]:
    """逐批生成目标卷章纲，yield (batch_chapters, batch_start, batch_end)。

    批间承接两条线：① 爽点钩子(prev_tail)；② 境界脊柱(realm_floor，单调不减、写库强保证)。
    """
    planned = int(target_volume.get("planned_chapters", cfg.volume_chapters))
    ctx["_target_volume"] = target_volume
    rmax = _realm_max(ctx)
    vr_lo = target_volume.get("realm_start_rank") or 1
    vr_hi = target_volume.get("realm_end_rank") or rmax
    accumulated: list[dict] = []
    prev_tail = ""
    running = int(vr_lo)  # 主角当前境界档，跨批延续
    for bs, be in _batch_ranges(planned, cfg.chapter_batch_size):
        ctx["_batch"] = {
            "batch_start": bs, "batch_end": be,
            "prev_tail": prev_tail, "realm_floor": running,
        }
        batch = await run_step(
            "chapter_outlines", ctx, call, cfg,
            meta={"batch_start": bs, "batch_end": be},
        )
        if not isinstance(batch, list):
            batch = []
        for i, ch in enumerate(batch):
            ch["chapter_number"] = len(accumulated) + i + 1
        running = _enforce_realm(batch, running, vr_hi, rmax)  # 写库前强制单调
        accumulated.extend(batch)
        prev_tail = _tail_of(batch)
        yield batch, bs, be
    ctx.pop("_batch", None)
    ctx.pop("_target_volume", None)
