"""
debrief.py — 章节复盘 AI 能力聚合壳

拆分说明：
  debrief_helpers.py  → 纯函数工具层（_VALID_PROMISE_TYPES / _clean_new_reader_promises /
                         _clean_fulfilled_promise_texts / split_foreshadow_updates）
  debrief_extract.py  → DebriefMixin（auto_extract_debrief）

本文件仅做重导出，保持调用方 `from app.services.ai.debrief import DebriefMixin` 不变。
"""
from __future__ import annotations

from app.services.ai.debrief_extract import DebriefMixin  # noqa: F401
from app.services.ai.debrief_helpers import (  # noqa: F401
    _clean_fulfilled_promise_texts,
    _clean_new_reader_promises,
    split_foreshadow_updates,
)
