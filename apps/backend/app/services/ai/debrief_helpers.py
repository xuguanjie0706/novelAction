"""
debrief_helpers.py — 复盘模块纯函数工具层

职责：
  _VALID_PROMISE_TYPES          → 允许的读者承诺类型枚举集合
  _clean_new_reader_promises    → 解析 auto_debrief 输出的新承诺列表
  _clean_fulfilled_promise_texts→ 解析本章已兑现承诺原文列表
  split_foreshadow_updates      → 将 AI 输出的 foreshadow_updates 拆分为埋/收两个数组
"""
from __future__ import annotations

import re

_VALID_PROMISE_TYPES = frozenset({
    "chapter_ending",
    "volume_ending",
    "name_implication",
    "chapter_comment_consensus",
    "protagonist_claim",
})


def _clean_new_reader_promises(raw_list) -> list[dict]:
    """解析 auto_debrief 的 new_reader_promises，供 chapter-debrief 落库。"""
    out: list[dict] = []
    for p in raw_list or []:
        if not isinstance(p, dict):
            continue
        text = (p.get("promise_text") or "").strip()
        if not text:
            continue
        ptype = p.get("promise_type") or "chapter_ending"
        if ptype not in _VALID_PROMISE_TYPES:
            ptype = "chapter_ending"
        try:
            window = max(0, min(50, int(p.get("expected_within_chapters") or 3)))
        except Exception:
            window = 3
        try:
            priority = max(1, min(5, int(p.get("priority") or 3)))
        except Exception:
            priority = 3
        try:
            audience = max(0, min(5, int(p.get("audience_aware") or 3)))
        except Exception:
            audience = 3
        out.append({
            "promise_text": text[:500],
            "promise_type": ptype,
            "expected_within_chapters": window,
            "priority": priority,
            "audience_aware": audience,
        })
    return out[:8]


def _clean_fulfilled_promise_texts(raw_list) -> list[str]:
    """解析本章已兑现承诺原文列表。"""
    out: list[str] = []
    for item in raw_list or []:
        text = (item if isinstance(item, str) else str(item or "")).strip()
        if text and text not in out:
            out.append(text[:500])
    return out[:12]


def split_foreshadow_updates(chapter_index: dict) -> dict:
    """将 AI 输出的 foreshadow_updates（统一格式）拆分为下游所需的两个数组。

    新格式：每条带显式 action（lay/develop/resolve）和 code 字段。
    兼容旧格式：若 foreshadow_updates 为空，则回退读取 actual_foreshadows_laid /
    actual_foreshadows_resolved（旧版 AI 输出或缓存数据）。

    Args:
        chapter_index: 章节索引 dict，含 foreshadow_updates（或旧格式字段）。

    Returns:
        {"actual_foreshadows_laid": [...], "actual_foreshadows_resolved": [...]}
        两数组的 item 均携带显式 code 字段（可为 None），供 foreshadow_payload_from_index_item 优先读取。
    """
    laid: list[dict] = []
    resolved: list[dict] = []

    raw_updates = chapter_index.get("foreshadow_updates") or []
    if raw_updates and isinstance(raw_updates, list):
        for item in raw_updates[:15]:
            if not isinstance(item, dict):
                continue
            desc = (item.get("description") or "").strip()
            if not desc:
                continue
            action = str(item.get("action") or "lay").strip().lower()
            # 显式 code 字段：统一规范化为 F-NNN 或 None
            raw_code = item.get("code")
            code: str | None = None
            if raw_code:
                m = re.search(r"F[-_ ]?(\d{1,4})", str(raw_code).strip(), flags=re.IGNORECASE)
                code = f"F-{int(m.group(1)):03d}" if m else None

            entry: dict = {
                "code": code,
                "title": (item.get("title") or "").strip()[:100] or None,
                "description": desc,
            }
            if action in ("lay",):
                dc = item.get("deadline_chapter")
                entry["deadline_chapter"] = int(dc) if isinstance(dc, (int, float)) else 0
                entry["status"] = "open"
                laid.append(entry)
            else:
                # develop / resolve 都归入已回收/推进数组，由 foreshadow.py 按 planned_action 处理
                entry["planned_action"] = "resolve" if action == "resolve" else "develop"
                resolved.append(entry)
    else:
        # ── 兼容旧格式（缓存或老版 AI 输出）──
        for item in (chapter_index.get("actual_foreshadows_laid") or [])[:10]:
            if not isinstance(item, dict) or not item.get("description"):
                continue
            dc = item.get("deadline_chapter")
            laid.append({
                "code": item.get("code") or None,
                "title": (item.get("title") or "").strip()[:100] or None,
                "description": item.get("description", ""),
                "status": item.get("status", "open"),
                "deadline_chapter": int(dc) if isinstance(dc, (int, float)) else 0,
            })
        for item in (chapter_index.get("actual_foreshadows_resolved") or [])[:10]:
            if not isinstance(item, dict) or not item.get("description"):
                continue
            resolved.append({
                "code": item.get("code") or None,
                "title": (item.get("title") or "").strip()[:100] or None,
                "description": item.get("description", ""),
                "planned_action": item.get("planned_action", "resolve"),
            })

    return {
        "actual_foreshadows_laid": laid,
        "actual_foreshadows_resolved": resolved,
    }
