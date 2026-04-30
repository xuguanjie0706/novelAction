"""作者可见的章节序号：与写作侧栏（大纲章标题）对齐。"""

from __future__ import annotations

import re
from typing import Optional

_CHAPTER_NUM_PREFIX = re.compile(r"^\s*第\s*0*(\d+)\s*章")


def display_chapter_number(title: Optional[str], sort_order: Optional[int]) -> int:
    """
    若标题以「第N章」开头（可含全角冒号前的空格），返回 N；
    否则退回全局顺位 sort_order + 1（与旧逻辑一致）。
    """
    raw = (title or "").strip()
    m = _CHAPTER_NUM_PREFIX.match(raw)
    if m:
        return max(1, int(m.group(1)))
    so = 0 if sort_order is None else int(sort_order)
    return max(1, so + 1)
