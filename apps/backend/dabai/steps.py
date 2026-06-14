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
        errors = schemas.validate_step(step, data, meta=meta)
        if not errors:
            return data
        last_err = "；".join(errors[:5])
        logger.warning("%s 校验未过(attempt=%d)：%s", step, attempt + 1, last_err)
        user = user + f"\n\n上次输出有问题，请修正后重新返回完整 JSON：{last_err}"
    raise DabaiStepError(f"{step} 连续 2 次失败：{last_err}")


def _batch_ranges(planned: int, size: int, start: int = 1) -> list[tuple[int, int]]:
    """切分章节区间，如 (60,30) → [(1,30),(31,60)]；start 支持增量补全从中途起批。"""
    size = max(5, size)
    return [(s, min(s + size - 1, planned)) for s in range(max(1, start), planned + 1, size)]


def _tail_of(batch: list[dict]) -> str:
    if not batch:
        return ""
    last = batch[-1]
    return (last.get("end_hook") or last.get("shuang_payoff") or "").strip()


def _after_outline_batch(ctx: dict, batch: list[dict]) -> None:
    """批后更新：已生成章纲累积 + 下批承接块（bootstrap 无 DB 路径）。"""
    if not batch:
        return
    from app.services.dabai.lab_narrative_state import (
        format_bridge_from_outline,
        format_generated_outlines_block,
    )
    acc = ctx.setdefault("generated_chapter_outlines", [])
    acc.extend(batch)
    ctx["generated_outlines_block"] = format_generated_outlines_block(acc)
    last = batch[-1]
    next_num = int(last.get("chapter_number") or 0) + 1
    ctx["bridge_block"] = format_bridge_from_outline(last, next_num)
    ctx["prev_tail"] = _tail_of(batch)


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


async def _gen_volume_single(
    ctx: dict, call: CallFn, cfg: DabaiConfig, *,
    planned: int, start_chapter: int, chapter_offset: int,
    prev_tail: str, realm_floor: int,
) -> tuple[list[dict], list[dict]] | None:
    """单次调用整卷（窗口）：beat_sequence + chapter_outlines 同一次推理产出。

    按次计费主路径：相比两段式（1+N 次）只花 1 次，且节拍表与五拍展开在
    同一上下文内自洽。失败返回 None，调用方降级两段式。
    """
    ctx["_batch"] = {
        "batch_start": start_chapter, "batch_end": planned,
        "global_start": chapter_offset + start_chapter,
        "global_end": chapter_offset + planned,
        "prev_tail": prev_tail, "realm_floor": realm_floor,
        "bridge_block": ctx.get("bridge_block") or "",
    }
    try:
        data = await run_step(
            "volume_chapters", ctx, call, cfg,
            meta={"batch_start": start_chapter, "batch_end": planned},
        )
    except DabaiStepError as exc:
        logger.warning("volume_chapters 单次整卷失败，将降级两段式：%s", exc)
        return None
    finally:
        ctx.pop("_batch", None)
    beats = data.get("beat_sequence") or []
    chapters = data.get("chapter_outlines") or []
    expected = planned - start_chapter + 1
    if not chapters or len(beats) != expected or len(chapters) != expected:
        logger.warning(
            "volume_chapters 章数不足（beat=%d chapter=%d 期望=%d），降级两段式",
            len(beats), len(chapters), expected,
        )
        return None
    base = chapter_offset + start_chapter
    for i, r in enumerate(beats):
        r["chapter_number"] = base + i
    for i, ch in enumerate(chapters):
        ch["chapter_number"] = base + i
    return beats, chapters


async def _gen_beat_rows(
    ctx: dict, call: CallFn, cfg: DabaiConfig, *,
    planned: int, start_chapter: int, chapter_offset: int,
    prev_tail: str, realm_floor: int, vr_hi: int | None, rmax: int | None,
) -> list[dict]:
    """阶段一：整卷（窗口）爽点节拍序列，超大卷按 beat_chunk_size 分段排。"""
    rows: list[dict] = []
    tail, running = prev_tail, realm_floor
    try:
        for s, e in _batch_ranges(planned, cfg.beat_chunk_size, start=start_chapter):
            ctx["_beat_window"] = {
                "global_start": chapter_offset + s, "global_end": chapter_offset + e,
                "prev_tail": tail, "realm_floor": running,
                "bridge_block": ctx.get("bridge_block") or "",
            }
            chunk = await run_step(
                "beat_sequence", ctx, call, cfg,
                meta={"batch_start": s, "batch_end": e},
            )
            if not isinstance(chunk, list):
                chunk = []
            for i, r in enumerate(chunk):
                r["chapter_number"] = chapter_offset + s + i
            running = _enforce_realm(chunk, running, vr_hi, rmax)
            if chunk:
                tail = (chunk[-1].get("one_line") or tail).strip() or tail
            rows.extend(chunk)
    finally:
        ctx.pop("_beat_window", None)
    return rows


async def aiter_chapter_batches(
    ctx: dict, call: CallFn, cfg: DabaiConfig, target_volume: dict,
    *,
    start_chapter: int = 1,
    chapter_offset: int = 0,
    prev_tail: str = "",
    realm_floor: int | None = None,
) -> AsyncIterator[tuple[list[dict], int, int]]:
    """两段式逐批生成目标卷章纲，yield (batch_chapters, global_start, global_end)。

    阶段一 beat_sequence：一次（或按 beat_chunk_size 分段）排好整卷节拍施工图，
    全局协调爽点阶梯/场景轮换/打脸对象轮换/境界爬升；失败则降级为直接分批展开。
    阶段二 chapter_outlines：按 chapter_batch_size 小批展开五拍，每批锁定对应节拍行；
    批后过 repair_batch（linter 问题回灌定向重写），写库前境界硬保证。

    批间承接两条线：① 爽点钩子(prev_tail)；② 境界脊柱(realm_floor，单调不减、写库强保证)。

    卷展开（写作期，卷2+ / 增量补全）专用参数：
      start_chapter: 卷内起始章（1-based）。未满卷增量补全时从已有章数+1 起批。
      chapter_offset: 全局章号偏移（= 之前各卷 planned_chapters 之和）。落库与 prompt
        展示均用全局章号（offset + 卷内章号），黄金前3章约束也按全局章号判定。
      prev_tail: 起步承接钩子。增量补全=本卷末章 end_hook；新展开卷=上一卷末章钩子。
      realm_floor: 起步境界档（增量补全取本卷已有末章 realm_rank），不低于卷区间下限。
    """
    from dabai.repair import repair_batch

    planned = cfg.outline_window_end(
        int(target_volume.get("planned_chapters", cfg.volume_chapters)),
        start_chapter,
    )
    ctx["_target_volume"] = target_volume
    rmax = _realm_max(ctx)
    vr_lo = target_volume.get("realm_start_rank") or 1
    vr_hi = target_volume.get("realm_end_rank") or rmax
    gf_name = (ctx.get("golden_finger") or {}).get("name", "")
    prev_tail = (prev_tail or "").strip()
    running = max(int(realm_floor or 0), int(vr_lo))  # 主角当前境界档，跨批延续
    ctx.setdefault("generated_chapter_outlines", [])
    ctx["prev_tail"] = prev_tail

    # ── 主路径：单次整卷 beat+五拍（按次计费；窗口 ≤ single_call_max_chapters）──
    window_n = planned - start_chapter + 1
    if window_n <= cfg.single_call_max_chapters:
        single = await _gen_volume_single(
            ctx, call, cfg, planned=planned, start_chapter=start_chapter,
            chapter_offset=chapter_offset, prev_tail=prev_tail, realm_floor=running,
        )
        if single is not None:
            beats, chapters = single
            running_start = running
            _enforce_realm(beats, running_start, vr_hi, rmax)
            ctx["beat_sequence"] = beats
            running = _enforce_realm(chapters, running_start, vr_hi, rmax)
            repaired = await repair_batch(
                ctx, call, cfg, chapters,
                realm_range=(vr_lo, vr_hi), realm_max=rmax,
                golden_finger_name=gf_name,
            )
            if repaired is not chapters:
                chapters = repaired
                _enforce_realm(chapters, running_start, vr_hi, rmax)
            yield chapters, chapter_offset + start_chapter, chapter_offset + planned
            ctx.pop("_target_volume", None)
            return
        # 单次失败 → 落回两段式（质量兜底优先于省调用）

    # ── 降级路径·阶段一：节拍序列（施工图）。失败仅再降级为直接分批 ─────────────
    beats: list[dict] = []
    try:
        beats = await _gen_beat_rows(
            ctx, call, cfg, planned=planned, start_chapter=start_chapter,
            chapter_offset=chapter_offset, prev_tail=prev_tail,
            realm_floor=running, vr_hi=vr_hi, rmax=rmax,
        )
    except DabaiStepError as exc:
        logger.warning("节拍序列生成失败，降级为直接分批展开：%s", exc)
    ctx["beat_sequence"] = beats  # 调用方负责持久化（bootstrap/卷展开各按卷键落 extra）

    # ── 阶段二：小批五拍展开 + 修复闭环 ─────────────────────────────────────────
    for bs, be in _batch_ranges(planned, cfg.chapter_batch_size, start=start_chapter):
        gbs, gbe = chapter_offset + bs, chapter_offset + be
        ctx["_batch"] = {
            "batch_start": bs, "batch_end": be,
            "global_start": gbs, "global_end": gbe,
            "prev_tail": prev_tail, "realm_floor": running,
            "bridge_block": ctx.get("bridge_block") or "",
            "beat_rows": [r for r in beats
                          if gbs <= int(r.get("chapter_number") or 0) <= gbe],
        }
        batch = await run_step(
            "chapter_outlines", ctx, call, cfg,
            meta={"batch_start": bs, "batch_end": be},
        )
        if not isinstance(batch, list):
            batch = []
        for i, ch in enumerate(batch):
            ch["chapter_number"] = gbs + i
        running_start = running
        running = _enforce_realm(batch, running_start, vr_hi, rmax)  # 写库前强制单调
        repaired = await repair_batch(
            ctx, call, cfg, batch,
            realm_range=(vr_lo, vr_hi), realm_max=rmax, golden_finger_name=gf_name,
        )
        if repaired is not batch:
            batch = repaired
            running = _enforce_realm(batch, running_start, vr_hi, rmax)
        _after_outline_batch(ctx, batch)
        prev_tail = ctx.get("prev_tail") or _tail_of(batch)
        yield batch, gbs, gbe
    ctx.pop("_batch", None)
    ctx.pop("_target_volume", None)
