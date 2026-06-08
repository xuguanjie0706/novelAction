"""编排薄壳：串联所有 step、累积上下文、跑 linter、落 JSON 产物。

薄壳只负责：步骤分发 + 上下文累积 + 异常处理 + 产物组装。
不写业务 prompt（在 prompts.py）、不写校验细节（在 schemas.py / linter.py）。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

from dabai import linter, steps
from dabai.config import DabaiConfig
from dabai.llm_client import DabaiLLM, LLMError

logger = logging.getLogger("dabai.pipeline")

OUTPUT_DIR = Path(__file__).parent / "outputs"

# 章纲步用特化入口，其余走通用 run_step
_SPECIAL: dict[str, Callable] = {
    "chapter_outlines": steps.run_chapter_outlines,
}


def _slug(text: str) -> str:
    keep = "".join(c for c in text if c.isalnum() or c in "一二三四五六七八九十")[:16]
    return keep or "untitled"


class BootstrapResult:
    """一次运行的完整产物 + 事件日志。"""

    def __init__(self, cfg: DabaiConfig):
        self.cfg = cfg
        self.ctx: dict[str, Any] = {"logline": cfg.logline}
        self.events: list[dict] = []
        self.linter_report: dict | None = None
        self.failed_steps: list[str] = []

    def emit(self, event: str, **kw):
        rec = {"event": event, "ts": round(time.time(), 3), **kw}
        self.events.append(rec)
        logger.info("%s %s", event, {k: v for k, v in kw.items() if k != "data"})

    def to_json(self) -> dict:
        return {
            "logline": self.cfg.logline,
            "meta": {
                "volume_count": self.cfg.volume_count,
                "volume_chapters": self.cfg.volume_chapters,
                "mock": self.cfg.mock,
                "model": self.cfg.model,
                "failed_steps": self.failed_steps,
            },
            "positioning": self.ctx.get("positioning"),
            "golden_finger": self.ctx.get("golden_finger"),
            "power_ladder": self.ctx.get("power_ladder"),
            "factions": self.ctx.get("factions"),
            "characters": self.ctx.get("characters"),
            "storylines": self.ctx.get("storylines"),
            "volumes": self.ctx.get("volumes"),
            "chapter_outlines": self.ctx.get("chapter_outlines"),
            "linter_report": self.linter_report,
            "events": self.events,
        }

    def save(self) -> Path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / f"bootstrap_{_slug(self.cfg.logline)}.json"
        path.write_text(
            json.dumps(self.to_json(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path


def run_bootstrap(cfg: DabaiConfig) -> BootstrapResult:
    """执行完整大白文 bootstrap 闭环。"""
    result = BootstrapResult(cfg)
    llm = DabaiLLM(cfg)
    result.emit("bootstrap_start", logline=cfg.logline, mock=cfg.mock,
                steps=cfg.active_steps())

    for step in cfg.active_steps():
        result.emit("step_start", step=step)
        try:
            runner = _SPECIAL.get(step)
            data = (runner(result.ctx, llm, cfg) if runner
                    else steps.run_step(step, result.ctx, llm, cfg))
            result.ctx[step] = data
            count = len(data) if isinstance(data, list) else 1
            result.emit("step_done", step=step, item_count=count)
        except LLMError as exc:
            result.failed_steps.append(step)
            result.emit("step_error", step=step, message=str(exc))
            logger.error("步骤 %s 失败，链路中断：%s", step, exc)
            break

    # ── 章纲 linter 闸门 ──────────────────────────────────────────────────────
    chapters = result.ctx.get("chapter_outlines")
    if chapters:
        report = linter.lint_chapters(chapters, cfg)
        result.linter_report = report.as_dict()
        result.emit("linter_done", status=report.status,
                    score=report.score(), issues=len(report.issues))

    result.emit("bootstrap_end", failed=result.failed_steps)
    return result
