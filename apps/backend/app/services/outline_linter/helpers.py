"""Linter 共用工具函数。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

PLACEHOLDER_VALUES = frozenset({
    "",
    "无",
    "（无）",
    "(无)",
    "暂无",
    "待定",
    "悬念",
    "留下悬念",
    "悬念丛生",
    "让读者期待",
    "主角沉思",
    "拭目以待",
})

VAGUE_END_HOOK_RE = re.compile(
    r"(悬念|期待|拭目以待|细思极恐|意味深长|欲知后事|且听下回)",
)

# 与 foreshadow_sync 同语法，用子串检测避免复杂字符类
FORESHADOW_LAY_MARK = "埋["
FORESHADOW_RESOLVE_MARK = "收["
FORESHADOW_HEAT_MARK = "加热["

VALID_PACING = frozenset({"fast", "normal", "slow", "climax"})


@dataclass
class ChapterSnapshot:
    """从 OutlineNode 提取的章纲快照，便于单测。"""

    id: str | None
    sort_order: int
    title: str
    summary: str | None
    hook: str | None
    highlight: str | None
    conflict: str | None
    pacing: str | None
    phase: str | None
    expected_words: int | None
    storyline_ids: list[Any]
    involved_character_ids: list[Any]
    power_milestone: str | None
    extra: dict[str, Any]

    @property
    def chapter_number(self) -> int:
        return self.sort_order + 1

    def end_hook_text(self) -> str:
        ex = self.extra or {}
        return (ex.get("end_hook") or self.highlight or "").strip()

    def ex_str(self, key: str) -> str:
        val = (self.extra or {}).get(key)
        return val.strip() if isinstance(val, str) else ""


def chapter_from_node(node: Any) -> ChapterSnapshot:
    return ChapterSnapshot(
        id=str(node.id) if getattr(node, "id", None) else None,
        sort_order=int(node.sort_order or 0),
        title=str(node.title or ""),
        summary=node.summary,
        hook=node.hook,
        highlight=node.highlight,
        conflict=node.conflict,
        pacing=node.pacing,
        phase=node.phase,
        expected_words=node.expected_words,
        storyline_ids=list(node.storyline_ids or []),
        involved_character_ids=list(node.involved_character_ids or []),
        power_milestone=node.power_milestone,
        extra=dict(node.extra or {}),
    )


def is_placeholder(text: str | None) -> bool:
    if not text:
        return True
    return text.strip() in PLACEHOLDER_VALUES


def is_vague_end_hook(text: str) -> bool:
    if not text or len(text) < 12:
        return True
    return bool(VAGUE_END_HOOK_RE.search(text))


def text_overlap(a: str, b: str, min_len: int = 2) -> bool:
    """两段文本是否存在长度 >= min_len 的公共子串（粗粒度承接检测）。"""
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return False
    if min_len <= 1:
        return bool(set(a) & set(b))
    for i in range(len(a) - min_len + 1):
        frag = a[i : i + min_len]
        if frag in b:
            return True
    return False


def extract_bigrams(text: str) -> set[str]:
    text = re.sub(r"\s+", "", text or "")
    if len(text) < 2:
        return set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


def bigram_overlap(a: str, b: str) -> bool:
    return bool(extract_bigrams(a) & extract_bigrams(b))


def count_face_slap_windows(chapters: list[ChapterSnapshot], window: int) -> list[int]:
    """返回每个窗口起点（0-based）内无打脸章的窗口起始索引。"""
    flags = [bool((ch.extra or {}).get("has_face_slap")) for ch in chapters]
    bad: list[int] = []
    for start in range(max(0, len(flags) - window + 1)):
        if not any(flags[start : start + window]):
            bad.append(start)
    return bad


def face_slap_bounds(pace_type: str, chapter_count: int) -> tuple[int, int, int]:
    """返回 (min_total, max_total, window_size)。"""
    pace = (pace_type or "medium").lower()
    if pace == "fast":
        window = 5
        min_total = max(1, (chapter_count + 4) // 5)
        max_total = max(min_total, (chapter_count + 1) // 2)
    elif pace == "slow":
        window = 12
        min_total = max(1, (chapter_count + 11) // 12)
        max_total = max(min_total, (chapter_count + 3) // 4)
    else:
        window = 8
        min_total = max(1, (chapter_count + 7) // 8)
        max_total = max(min_total, (chapter_count + 2) // 3)
    return min_total, max_total, window


def chapter_foreshadow_ops(ch: ChapterSnapshot) -> list[dict[str, Any]]:
    """本章伏笔 ops：优先结构化字段，回退 legacy 文本解析。"""
    extra = ch.extra or {}
    raw_ops = extra.get("foreshadow_ops")
    if isinstance(raw_ops, list) and raw_ops:
        from app.services.bootstrap.foreshadow_ops import normalize_op

        return [o for o in (normalize_op(x) for x in raw_ops) if o]

    from app.services.bootstrap.foreshadow_ops import legacy_string_to_ops

    return legacy_string_to_ops(ch.ex_str("foreshadow"))


def chapter_has_foreshadow_lay(ch: ChapterSnapshot) -> bool:
    """本章是否规划了埋伏笔（结构化或 legacy）。"""
    from app.services.bootstrap.foreshadow_ops import chapter_has_lay

    return chapter_has_lay(chapter_foreshadow_ops(ch))


def distinct_foreshadow_lay_lines(chapters: list[ChapterSnapshot]) -> set[str]:
    from app.services.bootstrap.foreshadow_ops import extract_lay_names

    themes: set[str] = set()
    for ch in chapters:
        for name in extract_lay_names(chapter_foreshadow_ops(ch)):
            themes.add(name[:40])
    return themes
