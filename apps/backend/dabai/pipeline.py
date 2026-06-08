"""编排薄壳（异步）：串联 step、累积上下文、跑 linter、产出事件流 / JSON。

三个入口：
  - aiter_bootstrap(cfg, call)：**异步生成器**，逐步 yield 事件（SSE 路由增量落库+流式）。
  - collect_bootstrap(cfg, call)：消费事件流组装 BootstrapResult（非流式）。
  - run_bootstrap(cfg)：同步封装（CLI），内部 asyncio.run + DabaiLLM 注入。

`call` 是注入式异步调用器（见 steps.CallFn）。薄壳只做分发/累积/异常，不碰 DB、不写 prompt。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from dabai import linter, steps
from dabai.config import DabaiConfig
from dabai.steps import CallFn, DabaiStepError

logger = logging.getLogger("dabai.pipeline")

OUTPUT_DIR = Path(__file__).parent / "outputs"

_SETTING_STEPS = {
    "benchmark", "positioning", "golden_finger", "power_ladder",
    "factions", "characters", "storylines", "volumes",
}

# 合并步：carrier 一次 LLM 调用同时产出多个 ctx 键；derived 复用同次结果，不再调 LLM。
# 合并动机：同类设定本就是一次连续推理，拆多次既费 token 又容易彼此对不齐。
_MERGE_CARRIERS: dict[str, tuple[str, ...]] = {
    "benchmark": ("benchmark", "positioning"),       # 对标分析 + 立项定位
    "golden_finger": ("golden_finger", "power_ladder"),  # 金手指 + 境界阶梯（力量体系）
    "factions": ("factions", "characters"),          # 势力 + 人物（阵营卡司）
}
_MERGE_DERIVED: dict[str, str] = {
    derived: carrier
    for carrier, keys in _MERGE_CARRIERS.items()
    for derived in keys if derived != carrier
}


def _count(data) -> int:
    return len(data) if isinstance(data, list) else 1


def _slug(text: str) -> str:
    keep = "".join(c for c in text if c.isalnum() or c in "一二三四五六七八九十")[:16]
    return keep or "untitled"


# ── 注入式调用器工厂 ─────────────────────────────────────────────────────────
def dabai_llm_call(cfg: DabaiConfig) -> CallFn:
    """mock / CLI：用 DabaiLLM（同步）包成异步 call。"""
    from dabai.llm_client import DabaiLLM
    llm = DabaiLLM(cfg)

    async def call(step: str, system: str, user: str, meta: dict | None) -> Any:
        return await asyncio.to_thread(llm.generate_json, step, system, user, meta)

    return call


# ── 异步事件生成器（流式核心）────────────────────────────────────────────────
async def aiter_bootstrap(cfg: DabaiConfig, call: CallFn) -> AsyncIterator[dict]:
    """逐步执行并 yield 事件（schema 见 README / 路由）。"""
    ctx: dict[str, Any] = {"logline": cfg.logline}
    failed: list[str] = []
    yield {"event": "bootstrap_start", "steps": cfg.active_steps()}

    for step in cfg.active_steps():
        yield {"event": "step_start", "step": step}
        try:
            if step in _MERGE_CARRIERS:
                # 合并步：一次 LLM 调用产出本组所有键，拆进 ctx
                combined = await steps.run_step(step, ctx, call, cfg)
                for key in _MERGE_CARRIERS[step]:
                    ctx[key] = combined.get(key)
                yield {"event": "step_done", "step": step,
                       "data": ctx[step], "count": _count(ctx[step])}
            elif step in _MERGE_DERIVED:
                # 已随 carrier 一次产出，不再单独调 LLM（共用同一次推理）
                data = ctx.get(step)
                yield {"event": "step_done", "step": step, "data": data, "count": _count(data)}
            elif step in _SETTING_STEPS:
                data = await steps.run_step(step, ctx, call, cfg)
                ctx[step] = data
                yield {"event": "step_done", "step": step, "data": data, "count": _count(data)}
            elif step == "chapter_outlines":
                vols = ctx.get("volumes") or []
                if not vols:
                    raise DabaiStepError("章纲步缺少卷骨架")
                all_ch: list[dict] = []
                async for batch, bs, be in steps.aiter_chapter_batches(ctx, call, cfg, vols[0]):
                    all_ch.extend(batch)
                    yield {"event": "chapter_batch", "data": batch,
                           "batch_start": bs, "batch_end": be}
                ctx["chapter_outlines"] = all_ch
                yield {"event": "step_done", "step": step, "data": all_ch,
                       "count": len(all_ch)}
        except DabaiStepError as exc:
            failed.append(step)
            yield {"event": "step_error", "step": step, "message": str(exc)}
            logger.error("步骤 %s 失败，链路中断：%s", step, exc)
            break

    report = None
    chapters = ctx.get("chapter_outlines")
    if chapters:
        vols = ctx.get("volumes") or []
        levels = (ctx.get("power_ladder") or {}).get("levels") or []
        ranks = [int(l.get("rank", 0)) for l in levels if str(l.get("rank", "")).strip()]
        v1 = vols[0] if vols else {}
        gf_name = (ctx.get("golden_finger") or {}).get("name", "")
        report = linter.lint_chapters(
            chapters, cfg,
            realm_max=max(ranks) if ranks else None,
            realm_range=(v1.get("realm_start_rank"), v1.get("realm_end_rank")),
            volumes=vols,
            golden_finger_name=gf_name,
        ).as_dict()
        yield {"event": "linter_done", "data": report}

    yield {"event": "bootstrap_end", "ctx": ctx,
           "linter_report": report, "failed_steps": failed}


# ── 非流式产物 ────────────────────────────────────────────────────────────────
class BootstrapResult:
    def __init__(self, cfg: DabaiConfig):
        self.cfg = cfg
        self.ctx: dict[str, Any] = {"logline": cfg.logline}
        self.linter_report: dict | None = None
        self.failed_steps: list[str] = []

    def to_json(self) -> dict:
        return {
            "logline": self.cfg.logline,
            "meta": {
                "volume_count": self.cfg.volume_count,
                "volume_chapters": self.cfg.volume_chapters,
                "chapter_batch_size": self.cfg.chapter_batch_size,
                "mock": self.cfg.mock, "model": self.cfg.model,
                "failed_steps": self.failed_steps,
            },
            "benchmark": self.ctx.get("benchmark"),
            "positioning": self.ctx.get("positioning"),
            "golden_finger": self.ctx.get("golden_finger"),
            "power_ladder": self.ctx.get("power_ladder"),
            "factions": self.ctx.get("factions"),
            "characters": self.ctx.get("characters"),
            "storylines": self.ctx.get("storylines"),
            "volumes": self.ctx.get("volumes"),
            "chapter_outlines": self.ctx.get("chapter_outlines"),
            "linter_report": self.linter_report,
        }

    def save(self) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / f"bootstrap_{_slug(self.cfg.logline)}.json"
        path.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path


async def collect_bootstrap(cfg: DabaiConfig, call: CallFn) -> BootstrapResult:
    """消费事件流组装 BootstrapResult（非流式 web / CLI 共用）。"""
    result = BootstrapResult(cfg)
    async for ev in aiter_bootstrap(cfg, call):
        if ev["event"] == "bootstrap_end":
            result.ctx = ev["ctx"]
            result.linter_report = ev.get("linter_report")
            result.failed_steps = ev.get("failed_steps", [])
    return result


def run_bootstrap(cfg: DabaiConfig) -> BootstrapResult:
    """同步封装（CLI）：DabaiLLM 注入 + asyncio.run。"""
    return asyncio.run(collect_bootstrap(cfg, dabai_llm_call(cfg)))
