"""写前预警 LLM 响应解析与结构化落库形状（与 writing_pre_warn.PreWriteWarnMixin 解耦）。"""
from __future__ import annotations

import re
from typing import Any

from app.services.bootstrap.parse import parse_json

_EMPTY_BRIDGE = {
    "needed": False,
    "technique_id": "",
    "technique_name": "",
    "instruction": "",
}


def looks_truncated_json(text: str) -> bool:
    """可见正文以 { 开头但未以 } 收尾，常见于 thinking 模型顶满 max_tokens。"""
    t = text.strip()
    if not t or "{" not in t:
        return False
    span = t[t.find("{") :]
    return not span.rstrip().endswith("}")


def _str(v: Any, fallback: str = "") -> str:
    return str(v).strip() if v else fallback


def _strlist(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if x]
    return []


def coerce_pre_write_warning_from_dict(data: dict) -> dict:
    """将 parse_json 产物规范为 pre_write_warning 落库 / SSE 共用 dict。"""
    risks = [
        r for r in (data.get("risks") or [])
        if isinstance(r, dict) and r.get("description")
    ]
    reminders = [str(r) for r in (data.get("reminders") or []) if r]
    has_critical = any(r.get("severity") in ("high", "critical") for r in risks)

    protagonist_fact_sheet = data.get("protagonist_fact_sheet") or {}
    if not isinstance(protagonist_fact_sheet, dict):
        protagonist_fact_sheet = {}

    writing_brief_raw = data.get("writing_brief") or {}
    if not isinstance(writing_brief_raw, dict):
        writing_brief_raw = {}
    writing_brief = {
        "opening_strategy": _str(writing_brief_raw.get("opening_strategy")),
        "conflict_structure": _str(writing_brief_raw.get("conflict_structure")),
        "closing_hook": _str(writing_brief_raw.get("closing_hook")),
        "word_rhythm": _str(writing_brief_raw.get("word_rhythm")),
    }

    _td_raw = data.get("transition_directive") or {}
    if not isinstance(_td_raw, dict):
        _td_raw = {}

    def _bridge(key: str) -> dict:
        b = _td_raw.get(key) or {}
        if not isinstance(b, dict):
            b = {}
        return {
            "needed": bool(b.get("needed", False)),
            "technique_id": _str(b.get("technique_id")),
            "technique_name": _str(b.get("technique_name")),
            "instruction": _str(b.get("instruction")),
        }

    return {
        "ok": not has_critical,
        "risk_count": len(risks),
        "protagonist_fact_sheet": {
            "realm": _str(protagonist_fact_sheet.get("realm")),
            "location": _str(protagonist_fact_sheet.get("location")),
            "key_skills": _strlist(protagonist_fact_sheet.get("key_skills")),
            "key_items": _strlist(protagonist_fact_sheet.get("key_items")),
            "forbidden": _strlist(protagonist_fact_sheet.get("forbidden")),
        },
        "writing_brief": writing_brief,
        "must_events": _strlist(data.get("must_events")),
        "hallucination_traps": _strlist(data.get("hallucination_traps")),
        "risks": risks[:15],
        "reminders": reminders[:10],
        "transition_directive": {
            "spatial_bridge": _bridge("spatial_bridge"),
            "realm_bridge": _bridge("realm_bridge"),
        },
        "chapter_lock_table": data.get("chapter_lock_table")
        if isinstance(data.get("chapter_lock_table"), dict)
        else {},
        "foreshadow_schedule_lock": data.get("foreshadow_schedule_lock")
        if isinstance(data.get("foreshadow_schedule_lock"), dict)
        else {},
    }


def parse_pre_write_warning_text(response: str) -> dict:
    """容错解析写前预警 JSON（走 bootstrap.parse_json）。"""
    data = parse_json(response)
    if not isinstance(data, dict):
        raise ValueError("pre_write_warning 根节点须为 JSON 对象")
    return coerce_pre_write_warning_from_dict(data)


def empty_pre_write_warning_error(exc: Exception, response: str) -> dict:
    """解析失败时的降级结构（侧栏可展示 error / raw）。"""
    return {
        "ok": False,
        "risk_count": 0,
        "protagonist_fact_sheet": {
            "realm": "",
            "location": "",
            "key_skills": [],
            "key_items": [],
            "forbidden": [],
        },
        "writing_brief": {
            "opening_strategy": "",
            "conflict_structure": "",
            "closing_hook": "",
            "word_rhythm": "",
        },
        "must_events": [],
        "hallucination_traps": [],
        "risks": [],
        "reminders": [],
        "transition_directive": {
            "spatial_bridge": dict(_EMPTY_BRIDGE),
            "realm_bridge": dict(_EMPTY_BRIDGE),
        },
        "chapter_lock_table": {},
        "foreshadow_schedule_lock": {},
        "error": str(exc),
        "raw": (response or "")[:1500],
        "parse_failed": True,
    }


def has_usable_pre_write_body(result: dict | None) -> bool:
    """是否含可展示/可注入正文的实质字段（非仅空壳或 parse_failed）。"""
    if not result or not isinstance(result, dict):
        return False
    if result.get("parse_failed") or result.get("error"):
        return False
    coerced = coerce_pre_write_warning_from_dict(result)
    pfs = coerced.get("protagonist_fact_sheet") or {}
    wb = coerced.get("writing_brief") or {}
    if (pfs.get("realm") or "").strip() or (wb.get("opening_strategy") or "").strip():
        return True
    if coerced.get("risks") or coerced.get("reminders"):
        return True
    if coerced.get("must_events") or coerced.get("hallucination_traps"):
        return True
    clt = coerced.get("chapter_lock_table") or {}
    if isinstance(clt, dict) and clt.get("has_prev") and (clt.get("locked_beats") or clt.get("forbidden_replays")):
        return True
    fsl = coerced.get("foreshadow_schedule_lock") or {}
    if isinstance(fsl, dict) and fsl.get("has_schedule") and (
        fsl.get("forbidden_early_plants") or fsl.get("allowed_this_chapter")
    ):
        return True
    return False
