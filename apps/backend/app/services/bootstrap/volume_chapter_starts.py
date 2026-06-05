"""卷级全书章号起始（跨卷累计，与 chapter_index.build_volume_start_map 一致）。"""
from __future__ import annotations

import re
from typing import Any

_CHAPTER_REF_RE = re.compile(r"(\d+)(?:-(\d+))?章")


def planned_chapters_value(raw: Any, default: int = 30) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    if n < 15:
        return default
    return min(n, 80)


def compute_chapter_starts(planned_list: list[int]) -> list[int]:
    """按各卷 planned_chapters 累加，返回每卷第 1 章的全书章号。"""
    starts: list[int] = []
    cursor = 1
    for planned in planned_list:
        starts.append(cursor)
        cursor += max(planned, 1)
    return starts


def shift_chapter_refs_in_text(text: str, start_global: int) -> str:
    """将节奏骨架等文案中的「本卷内章号」展示为全书章号（仅展示，不改存储）。"""
    if start_global <= 1 or not (text or "").strip():
        return text or ""
    offset = start_global - 1

    def _repl(m: re.Match[str]) -> str:
        a = int(m.group(1)) + offset
        b = m.group(2)
        if b is not None:
            return f"{a}-{int(b) + offset}章"
        return f"{a}章"

    return _CHAPTER_REF_RE.sub(_repl, text)


def format_volume_chapter_label(local_ch: int, start_global: int) -> str:
    """展示用章号标签：首卷简写，后续卷双标全书+本卷。"""
    if local_ch < 1:
        return "第 ? 章"
    if start_global <= 1:
        return f"第 {local_ch} 章"
    global_ch = start_global + local_ch - 1
    return f"全书第 {global_ch} 章（本卷第 {local_ch} 章）"


def build_volume_global_ranges_block(planned_list: list[int]) -> str:
    """注入 Step 9 prompt：各卷全书章号分段（节拍仍填本卷内章号）。"""
    if not planned_list:
        return ""
    lines = [
        "\n【全书章号分段（对齐用；beat_highlights / pacing_skeleton 仍填**本卷内**1~planned_chapters）】",
    ]
    starts = compute_chapter_starts(planned_list)
    for i, planned in enumerate(planned_list):
        start = starts[i]
        end = start + planned - 1
        lines.append(
            f"  第{i + 1}卷：全书约第{start}–{end}章（本卷内第1–{planned}章）"
        )
    lines.append(
        "  ⚠️ 第2卷起须承接前卷剧情与悬念，禁止每卷都写成「全书第1章重生/入门」式重置；"
        "chapter_hint 禁止填全书累计章号。"
    )
    return "\n".join(lines) + "\n"
