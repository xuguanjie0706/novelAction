"""
debrief_character_sync — 从 chapter_index 补全缺失的 character_updates。

队列自动复盘时，模型常把境界/位置写进 core_events 却漏写 character_updates，
导致 characters 表滞后而 chapter_index 正确。本模块在 auto-debrief 与 chapter-debrief
提交前做确定性补全（仅当索引与库内状态不一致且尚无对应更新项时）。
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_SENT_SPLIT = re.compile(r"[。；！？\n]+")
_REALM_AFTER_VERB = re.compile(
    r"(?:突破至|晋升至|晋升|达到|修为[^，。]{0,24}?达到|升至|突破到|连破[^，。]{0,16}达到|凝为|迈入)"
    r"[「『]?"
    r"([\u4e00-\u9fff]{1,8}境(?:[一二三四五六七八九十百千\d]+重)?(?:巅峰|大圆满|圆满)?)"
)
_REALM_INLINE = re.compile(
    r"([\u4e00-\u9fff]{1,6}境(?:[一二三四五六七八九十百千\d]+重)?(?:巅峰|大圆满|圆满)?)"
)
_REALM_VALID = re.compile(
    r"^[\u4e00-\u9fff]{1,6}境(?:[一二三四五六七八九十百千\d]+重)?(?:巅峰|大圆满|圆满)?$"
)
_REALM_CONTEXT = re.compile(r"突破|晋升|达到|修为|境界|连破|凝为|迈入|升至")
_LOC_AFTER_PREP = re.compile(
    r"(?:位于|在|踏入|进入|深入|赶往|回到|退入|困于|爬向|奔向)"
    r"([\u4e00-\u9fff]{2,28}(?:火脉|脉|秘境|柴房|殿|阁|池|谷|城|府|街|巷|禁地|通道|地道|密室|祖祠|演武场))"
)


def _norm(s: str | None) -> str:
    return (s or "").strip()


def _event_lines(chapter_index: dict | None) -> list[str]:
    if not chapter_index or not isinstance(chapter_index, dict):
        return []
    lines: list[str] = []
    for item in chapter_index.get("core_events") or []:
        if isinstance(item, str) and item.strip():
            lines.append(item.strip())
        elif isinstance(item, dict):
            text = (
                item.get("description")
                or item.get("event")
                or item.get("note")
                or ""
            )
            if str(text).strip():
                lines.append(str(text).strip())
    return lines


def _clean_realm_label(raw: str) -> str | None:
    label = re.sub(r"^修为达", "", _norm(raw))
    if not label or "境" not in label:
        return None
    m = _REALM_INLINE.search(label)
    if not m:
        return None
    label = _norm(m.group(1))
    if not _REALM_VALID.match(label):
        return None
    return label


def _extract_realm(sentence: str) -> str | None:
    m = _REALM_AFTER_VERB.search(sentence)
    if m:
        return _clean_realm_label(m.group(1))
    if "境" not in sentence or not _REALM_CONTEXT.search(sentence):
        return None
    last: str | None = None
    for m in _REALM_INLINE.finditer(sentence):
        cleaned = _clean_realm_label(m.group(1))
        if cleaned:
            last = cleaned
    return last


def _extract_location(sentence: str) -> str | None:
    m = _LOC_AFTER_PREP.search(sentence)
    if not m:
        return None
    loc = _norm(m.group(1))[:200]
    if any(bad in loc for bad in ("遭遇", "死士", "城主府", "拦截", "袭杀")):
        return None
    return loc


def _sentences_with_name(text: str, name: str) -> list[str]:
    if not name or name not in text:
        return []
    return [s for s in _SENT_SPLIT.split(text) if name in s]


def _infer_from_events(
    name: str,
    events: list[str],
    baseline_realm: str,
    baseline_location: str,
) -> dict[str, Any]:
    """从含该角色姓名的 event 句推断最新境界/位置（取最后一条命中）。"""
    realm, realm_reason, location, location_reason = "", "", "", ""
    for line in events:
        for sent in _sentences_with_name(line, name):
            r = _extract_realm(sent)
            if r:
                realm = r
                realm_reason = sent.strip()
            loc = _extract_location(sent)
            if loc:
                location = loc
                location_reason = sent.strip()
    out: dict[str, Any] = {}
    if realm and realm != baseline_realm:
        out["current_realm"] = realm[:100]
        out["realm_change_reason"] = realm_reason[:500]
    if location and location != baseline_location:
        out["current_location"] = location[:200]
        out["location_change_reason"] = location_reason[:500]
    return out


def supplement_character_updates_from_chapter_index(
    character_updates: list[dict],
    chapter_index: dict | None,
    character_states: list[dict],
) -> list[dict]:
    """
    当 AI 未输出 character_updates 时，从 chapter_index.core_events 补全。

    Returns:
        仅包含**新增**补全条目的列表（不含已有 character_updates 的副本）。
    """
    events = _event_lines(chapter_index)
    if not events:
        return []

    event_blob = "\n".join(events)
    covered_ids = {
        str(u.get("character_id"))
        for u in character_updates
        if u.get("character_id")
    }
    supplemented: list[dict] = []

    for st in character_states:
        cid = str(st.get("id") or "")
        name = _norm(st.get("name"))
        if not cid or not name or name not in event_blob:
            continue
        if cid in covered_ids:
            continue
        inferred = _infer_from_events(
            name,
            events,
            _norm(st.get("current_realm")),
            _norm(st.get("current_location")),
        )
        if not inferred:
            continue
        row = {
            "character_id": cid,
            "character_name": name,
            **inferred,
        }
        supplemented.append(row)
        covered_ids.add(cid)
        logger.info(
            "debrief_character_sync: supplemented %s from chapter_index (%s)",
            name,
            ", ".join(f"{k}={v!r}" for k, v in inferred.items()),
        )

    return supplemented


def merge_character_updates_for_debrief(
    character_updates: list[dict],
    chapter_index: dict | None,
    character_states: list[dict],
) -> list[dict]:
    """合并已有 updates 与索引补全；补全项不覆盖已有非空字段。"""
    extra = supplement_character_updates_from_chapter_index(
        character_updates, chapter_index, character_states,
    )
    by_id: dict[str, dict] = {}
    for raw in character_updates:
        if not isinstance(raw, dict):
            continue
        cid = str(raw.get("character_id") or "")
        if cid:
            by_id[cid] = dict(raw)

    for row in extra:
        cid = str(row.get("character_id") or "")
        if not cid:
            continue
        if cid not in by_id:
            by_id[cid] = row
            continue
        prev = by_id[cid]
        for key in (
            "current_realm", "realm_change_reason", "current_location",
            "location_change_reason", "current_status", "realm_rank",
        ):
            if row.get(key) is not None and not prev.get(key):
                prev[key] = row[key]

    return list(by_id.values())
