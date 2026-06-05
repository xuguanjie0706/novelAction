"""质检根因台账 —— 对外 schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class QualityRootCauseOut(BaseModel):
    id: UUID
    project_id: UUID
    chapter_id: Optional[UUID] = None
    source_chapter_number: int
    run_id: str
    item_kind: str
    dimension: str
    score: Optional[int] = None
    severity: str
    problem_summary: str
    root_cause_category: str
    root_cause_detail: Optional[str] = None
    code_fix_suggestion: Optional[str] = None
    evidence: dict = {}
    analysis_status: str
    occurrence_count: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RootCauseAggregateRow(BaseModel):
    """聚合视图：按根因分类或维度统计的高频行。"""

    key: str
    label: str
    total_occurrences: int
    distinct_items: int


class RootCauseAnalyzeRequest(BaseModel):
    chapter_id: UUID
    model_profile: str = "local"
    llm_provider_id: Optional[UUID] = None
