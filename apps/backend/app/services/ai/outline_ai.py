"""
outline_ai.py — 大纲 AI 能力聚合壳

拆分说明：
  outline_ai_expand.py  → OutlineExpandMixin  (expand_outline / plan_full_structure)
  outline_ai_quality.py → OutlineQualityMixin (_ISSUE_TYPE_REPAIR_HINTS /
                          _build_issue_type_hints / outline_quality_check / outline_repair_plan)

本文件仅做组合继承，保持调用方 `from app.services.ai.outline_ai import OutlineMixin` 不变。
"""
from __future__ import annotations

from app.services.ai.outline_ai_expand import OutlineExpandMixin  # noqa: F401
from app.services.ai.outline_ai_quality import OutlineQualityMixin  # noqa: F401


class OutlineMixin(OutlineExpandMixin, OutlineQualityMixin):  # type: ignore[misc]
    """大纲扩写 + 质检修复能力组合（薄壳，逻辑分散在两个子 Mixin）。"""
