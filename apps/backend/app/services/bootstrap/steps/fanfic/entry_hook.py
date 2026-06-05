"""Bootstrap Fanfic：切入点/开局落差（映射 contrast_design 供金手指复用）。"""
from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.json_once import call_bootstrap_json_once
from app.services.bootstrap.steps.fanfic._helpers import fanfic_meta_block, persist_extra

_STEP = "fanfic_entry"


async def gen_entry_hook(svc: Any, project: Project, ctx: dict) -> dict:
    system = "你是番茄同人开局设计专家。开局须在800字内给出强钩子。只返回 JSON。"
    fp = ctx.get("fanfic_positioning") or {}
    dev = ctx.get("fanfic_deviation") or {}
    prompt = f"""{fanfic_meta_block(ctx)}
同人类型：{fp.get('fanfic_trope_label', '')}
分歧点：{dev.get('divergence_point', '')}
创意：{ctx['logline']}

返回 JSON（字段名与番茄落差工程兼容）：
{{
  "initial_state_headline": "主角开局处境（含身份+具体事件，20字内）",
  "humiliation_scenes": ["羞辱/压抑场景1", "场景2"],
  "protagonist_pain_point": "主角最痛处（20字内）",
  "trigger_event": "金手指/穿书/重生/分歧触发事件（须具体，800字内发生）",
  "trigger_word_estimate": "约第XXX字",
  "final_destination": "读者期待的终态画面（一句话）",
  "contrast_ratio_note": "落差感说明（30字内）",
  "entry_chapter_hint": "建议切入原著第几章/什么事件前后（同人专用）"
}}"""

    def _validate(data: Any) -> str | None:
        if not isinstance(data, dict):
            return "须为 JSON 对象"
        if not data.get("initial_state_headline") or not data.get("trigger_event"):
            return "initial_state_headline / trigger_event 必填"
        return None

    data = await call_bootstrap_json_once(
        svc,
        step=_STEP,
        system=system,
        prompt=prompt,
        task="bootstrap.positioning",
        validate=_validate,
    )
    persist_extra(project, svc, "fanfic_entry", data)
    ctx["fanfic_entry"] = data
    ctx["contrast_design"] = {
        "initial_state_headline": data["initial_state_headline"],
        "humiliation_scenes": data.get("humiliation_scenes") or [],
        "protagonist_pain_point": data.get("protagonist_pain_point", ""),
        "trigger_event": data["trigger_event"],
        "trigger_word_estimate": data.get("trigger_word_estimate", ""),
        "final_destination": data.get("final_destination", ""),
        "contrast_ratio_note": data.get("contrast_ratio_note", ""),
    }
    return data
