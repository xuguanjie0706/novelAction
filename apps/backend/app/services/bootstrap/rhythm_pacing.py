"""rhythm_map.chapter_tags → 卷级 pacing_skeleton 的压缩、修复与展示。"""
from __future__ import annotations

import re
from typing import Any

DRY_TYPES = frozenset({"progress", "transition"})
WIN_TYPES = frozenset({"big_win", "small_win"})

_TAG_ZH = {
    "big_win": "大打脸",
    "small_win": "小爽",
    "progress": "推进",
    "transition": "过渡",
}

_MECHANICAL_SKELETON_RE = re.compile(r"第\d+·(progress|small_win|big_win|transition)")
_TAG_STYLE_SKELETON_RE = re.compile(r"章(推进|小爽|大打脸|过渡)")


def is_mechanical_tag_skeleton(text: str) -> bool:
    """识别 fanqie_normalize 旧版逐章打标串（第N·type → …）。"""
    s = (text or "").strip()
    if not s:
        return False
    return bool(_MECHANICAL_SKELETON_RE.search(s))


def is_tag_style_skeleton(text: str) -> bool:
    """识别 rhythm 打标压缩串（1章推进/2章小爽），非 Step 9 叙事章段。"""
    s = (text or "").strip()
    if not s or is_mechanical_tag_skeleton(s):
        return False
    return bool(_TAG_STYLE_SKELETON_RE.search(s))


def is_semantic_narrative_skeleton(text: str) -> bool:
    """Step 9 卷导演单语义骨架（如 1-5密钩铺屈辱/59-73章矿场蛰伏）。"""
    s = (text or "").strip()
    if not s:
        return False
    if is_mechanical_tag_skeleton(s) or is_tag_style_skeleton(s):
        return False
    return not needs_rhythm_skeleton_refresh(s)


def needs_rhythm_skeleton_refresh(text: str) -> bool:
    """需从 rhythm_map 重建成宏段骨架（含逐章叙事、机械打标）。"""
    s = (text or "").strip()
    if not s:
        return True
    if is_mechanical_tag_skeleton(s) or is_tag_style_skeleton(s):
        return True
    parts = [p.strip() for p in s.split("/") if p.strip()]
    if len(parts) <= 3:
        return False
    ranged = sum(1 for p in parts if re.match(r"^\d+-\d+章", p))
    return ranged < len(parts) / 2


def _safe_ch(tag: dict) -> int | None:
    raw = tag.get("ch")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _sorted_tags(tags: list) -> list[dict]:
    out: list[dict] = []
    for item in tags:
        if not isinstance(item, dict):
            continue
        ch = _safe_ch(item)
        if ch is None or ch < 1:
            continue
        out.append({**item, "ch": ch})
    return sorted(out, key=lambda t: t["ch"])


def repair_rhythm_tags(tags: list) -> tuple[list[dict], list[str]]:
    """修复节奏断裂：连续无爽章、big_win 间隔过长等。

    Returns:
        (repaired_tags, repair_notes)
    """
    sorted_tags = _sorted_tags(tags)
    if not sorted_tags:
        return [], []

    repaired = [dict(t) for t in sorted_tags]
    notes: list[str] = []

    def _fix_dry_streaks() -> int:
        changed = 0
        streak = 0
        for i, tag in enumerate(repaired):
            if str(tag.get("type") or "") in DRY_TYPES:
                streak += 1
                if streak >= 2:
                    ch = repaired[i].get("ch")
                    repaired[i]["type"] = "small_win"
                    repaired[i]["note"] = (repaired[i].get("note") or "节奏修复补爽")[:80]
                    notes.append(f"第{ch}章由无爽章升格为小爽")
                    changed += 1
                    streak = 0
            else:
                streak = 0
        return changed

    def _fix_dense_small_wins() -> int:
        changed = 0
        streak = 0
        for i, tag in enumerate(repaired):
            if tag.get("type") == "small_win":
                streak += 1
                if streak >= 2:
                    ch = repaired[i].get("ch")
                    repaired[i]["type"] = "progress"
                    notes.append(f"第{ch}章小爽过密，改为推进")
                    changed += 1
                    streak = 0
            else:
                streak = 0
        return changed

    # 两类修复会互相触发，迭代至稳定（通常 ≤3 轮）
    for _ in range(5):
        c1 = _fix_dry_streaks()
        c2 = _fix_dense_small_wins()
        if c1 + c2 == 0:
            break

    # 3) 前 10 章无 big_win → 优先把第 3–5 章的 small_win 升格
    first_10 = [t for t in repaired if t["ch"] <= 10]
    if first_10 and not any(t.get("type") == "big_win" for t in first_10):
        for t in first_10:
            if t.get("type") == "small_win" and 3 <= t["ch"] <= 5:
                t["type"] = "big_win"
                notes.append(f"第{t['ch']}章升格为首段大打脸（前10章缺大爽点）")
                break

    # 4) big_win 间隔超 15 章 → 间隔中点补 small_win
    big_chs = [t["ch"] for t in repaired if t.get("type") == "big_win"]
    for i in range(len(big_chs) - 1):
        gap = big_chs[i + 1] - big_chs[i]
        if gap <= 15:
            continue
        target = big_chs[i] + gap // 2
        for t in repaired:
            if t["ch"] == target and t.get("type") in DRY_TYPES:
                t["type"] = "small_win"
                notes.append(f"第{target}章补小爽（big_win 间隔{gap}章过长）")
                break

    return repaired, notes


def detect_dry_spells(tags: list) -> list[str]:
    """检测连续无爽章（progress/transition）与连续 transition。"""
    warnings: list[str] = []
    streak = 0
    streak_start = 0
    for item in _sorted_tags(tags):
        t = str(item.get("type") or "")
        if t in DRY_TYPES:
            if streak == 0:
                streak_start = item["ch"]
            streak += 1
            if streak > 2:
                warnings.append(
                    f"第{streak_start}-{item['ch']}章连续无爽章{streak}章，需补充爽点"
                )
        else:
            streak = 0
    return warnings


def _segment_label(tags_in_group: list[dict], t_type: str) -> str:
    """章段文案：优先 rhythm note（叙事），与 Step 9 pacing_skeleton 对齐。"""
    notes = [
        (t.get("note") or "").strip()
        for t in tags_in_group
        if (t.get("note") or "").strip() and (t.get("note") or "").strip() != "节奏修复补爽"
    ]
    if notes:
        if len(notes) == 1:
            return notes[0][:28]
        return f"{notes[0][:16]}…{notes[-1][:10]}"[:28]
    return _TAG_ZH.get(t_type, t_type)


_TYPE_RANK = {"big_win": 0, "small_win": 1, "progress": 2, "transition": 3}


def build_macro_pacing_skeleton_from_tags(
    tags: list,
    *,
    planned_chapters: int = 30,
    target_segments: int = 5,
) -> str:
    """按卷长切宏段（与 Step 9 多卷骨架同构，如 1-15章矿场蛰伏）。"""
    sorted_tags = _sorted_tags(tags)
    if not sorted_tags:
        return ""

    hi = min(planned_chapters, sorted_tags[-1]["ch"])
    lo = 1
    span = hi - lo + 1
    n_seg = max(2, min(target_segments, span))
    bucket_size = max(1, (span + n_seg - 1) // n_seg)

    by_ch = {t["ch"]: t for t in sorted_tags}
    segments: list[str] = []
    start = lo
    while start <= hi and len(segments) < n_seg:
        end = min(start + bucket_size - 1, hi)
        bucket_tags = [by_ch[c] for c in range(start, end + 1) if c in by_ch]
        if not bucket_tags:
            start = end + 1
            continue
        anchor = min(
            bucket_tags,
            key=lambda t: (_TYPE_RANK.get(str(t.get("type") or ""), 9), t["ch"]),
        )
        label = _segment_label([anchor], str(anchor.get("type") or "progress"))
        if end > start:
            segments.append(f"{start}-{end}章{label}")
        else:
            segments.append(f"{start}章{label}")
        start = end + 1

    return "/".join(segments)


def build_pacing_skeleton_from_tags(
    tags: list,
    *,
    preview_chapters: int = 30,
    max_segments: int = 6,
) -> str:
    """把 chapter_tags 压成「章段+叙事」骨架（对齐 Step 9 pacing_skeleton 契约）。"""
    sorted_tags = _sorted_tags(tags)
    if not sorted_tags:
        return ""

    preview = [t for t in sorted_tags if t["ch"] <= preview_chapters]
    if not preview:
        preview = sorted_tags

    segments: list[str] = []
    i = 0
    while i < len(preview) and len(segments) < max_segments:
        tag = preview[i]
        t_type = str(tag.get("type") or "progress")
        start_ch = tag["ch"]
        end_ch = start_ch
        group = [tag]
        j = i + 1
        while j < len(preview) and preview[j].get("type") == t_type:
            group.append(preview[j])
            end_ch = preview[j]["ch"]
            j += 1

        label = _segment_label(group, t_type)
        if end_ch > start_ch:
            seg = f"{start_ch}-{end_ch}章{label}"
        else:
            seg = f"{start_ch}章{label}"

        segments.append(seg)
        i = j

    tail = ""
    last_preview_ch = preview[-1]["ch"] if preview else 0
    last_tag_ch = sorted_tags[-1]["ch"]
    if last_tag_ch > last_preview_ch:
        tail = f"/…至第{last_tag_ch}章"

    return "/".join(segments) + tail


def refresh_opening_volume_pacing_skeleton(
    existing: str,
    tags: list,
    *,
    preview_chapters: int = 30,
) -> str:
    """第一卷 pacing_skeleton：保留 Step 9 叙事骨架，仅升级机械/打标串。"""
    current = (existing or "").strip()
    if current and is_semantic_narrative_skeleton(current):
        return current[:200]
    if not tags:
        return current[:200]
    built = build_macro_pacing_skeleton_from_tags(
        tags,
        planned_chapters=preview_chapters,
        target_segments=5,
    )
    return built[:200] if built else current[:200]


def apply_rhythm_to_pacing_skeleton(
    existing: str,
    tags: list,
    *,
    preview_chapters: int = 30,
) -> str:
    """兼容旧名；见 refresh_opening_volume_pacing_skeleton。"""
    return refresh_opening_volume_pacing_skeleton(
        existing, tags, preview_chapters=preview_chapters,
    )
