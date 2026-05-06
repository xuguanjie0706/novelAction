"""作者可见的章节序号：与写作侧栏（大纲章标题）对齐。"""

from __future__ import annotations

import re
from typing import Optional

_CHAPTER_NUM_PREFIX = re.compile(r"^\s*第\s*0*(\d+)\s*章")
_CHAPTER_TITLE_PREFIX = re.compile(r"^\s*第\s*0*(\d+)\s*章\s*[:：]?\s*(.*)$")


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


def normalize_chapter_plan_title(number: int, raw_title: Optional[str]) -> str:
    """
    统一章节计划标题为「第N章：标题」。

    - 输入已带「第X章[:：]」前缀时，仅保留其正文部分，避免双前缀。
    - 输入为空时，兜底为「未命名」。
    """
    safe_num = max(1, int(number or 1))
    title_text = (raw_title or "").strip()
    match = _CHAPTER_TITLE_PREFIX.match(title_text)
    if match:
        title_text = (match.group(2) or "").strip()
    if not title_text:
        title_text = "未命名"
    return f"第{safe_num}章：{title_text}"
