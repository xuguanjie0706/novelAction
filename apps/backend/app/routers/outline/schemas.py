"""大纲路由 Pydantic 模型（与前端 / OpenAPI 契约对齐）。"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel

# 工作流进度推送（质检 / 修复）
OutlineProgressPublisher = Callable[[dict[str, Any]], Awaitable[None]]


class ProtagonistRealmMilestoneOut(BaseModel):
    chapter_number: int
    chapter_title: str
    realm_name: str
    realm_rank: int
    character_change: str
    source: str = "outline"  # outline | debrief


class ProtagonistRealmTimelineOut(BaseModel):
    """只读：大纲「人物变化」+ 正文复盘提交时写入的主角境界快照，合并为一条创新高时间轴。"""

    protagonist_display_name: Optional[str] = None
    protagonist_anchor_names: list[str] = []
    has_realm_whitelist: bool
    anchored: bool
    chapter_plans_scanned: int
    debrief_snapshots: int = 0
    milestones: list[ProtagonistRealmMilestoneOut]
    source: str = "outline+debrief"


class StoryTimelineLaneOut(BaseModel):
    id: str
    label: str
    description: Optional[str] = None


class StoryTimelineBarOut(BaseModel):
    id: str
    lane: str
    label: str
    start_chapter: int
    end_chapter: int
    status: Optional[str] = None
    detail: Optional[str] = None


class StoryTimelineOut(BaseModel):
    """全书章序横轴 + 多泳道甘特条（卷/章/故事线/势力/伏笔/承诺/境界）。"""

    max_chapter: int
    chapter_plan_count: int = 0
    written_chapter_count: int = 0
    lanes: list[StoryTimelineLaneOut]
    bars: list[StoryTimelineBarOut]


class PowerTimelineRowOut(BaseModel):
    volume_order: int
    volume_id: str
    volume_title: str
    phase: str = ""
    protagonist_realm_start: Optional[str] = None
    protagonist_rank_start: Optional[int] = None
    protagonist_realm_end: Optional[str] = None
    protagonist_rank_end: Optional[int] = None
    boss_name: Optional[str] = None
    boss_character_id: Optional[str] = None
    boss_realm: Optional[str] = None
    boss_major_rank: Optional[int] = None
    boss_effective_score: Optional[float] = None
    boss_vs_prev_major: str
    boss_vs_prev_effective: str
    boss_vs_protagonist_end_delta: Optional[int] = None


class RealmScaleLevelOut(BaseModel):
    rank: int
    name: str


class PowerTimelinePointOut(BaseModel):
    volume_order: int
    realm_label: str
    major_rank: int
    effective_score: Optional[float] = None
    point_kind: str
    phase: str = ""
    boss_name: Optional[str] = None


class PowerTimelineChartOut(BaseModel):
    protagonist: list[PowerTimelinePointOut]
    boss: list[PowerTimelinePointOut]


class CharacterRealmSegmentOut(BaseModel):
    volume_order: int
    realm_label: str
    major_rank: int
    effective_score: float
    slot: str


class CharacterRealmLaneOut(BaseModel):
    character_id: Optional[str] = None
    display_name: str
    role: str = "supporting"
    character_tier: str = "plot"
    segments: list[CharacterRealmSegmentOut]


class PowerTimelineOut(BaseModel):
    updated_at: Optional[str] = None
    rows: list[PowerTimelineRowOut]
    realm_scale: list[RealmScaleLevelOut] = []
    chart: PowerTimelineChartOut = PowerTimelineChartOut(protagonist=[], boss=[])
    character_lanes: list[CharacterRealmLaneOut] = []
    volume_count: int = 0


class ChapterPlansClearResult(BaseModel):
    deleted: int


class ExpandRequest(BaseModel):
    node_id: str
    chapter_count: int = 10
    model_profile: str = "default"  # default / gemini
    llm_provider_id: Optional[UUID] = None


class FullGenerateRequest(BaseModel):
    # scale_hint 已废弃：卷章数现在由 project.target_words 驱动。
    scale_hint: str = "auto"
    theme_statement: Optional[str] = None
    model_profile: str = "default"
    llm_provider_id: Optional[UUID] = None
    clear_existing: bool = False


class OutlineQualityCheckRequest(BaseModel):
    theme_statement: Optional[str] = None
    model_profile: str = "gemini"
    llm_provider_id: Optional[UUID] = None
    scope: Literal["all", "volume", "book"] = "all"
    volume_node_id: Optional[UUID] = None


class OutlineQualityWorkflowStartResponse(BaseModel):
    run_id: str


class OutlineRepairRequest(BaseModel):
    theme_statement: Optional[str] = None
    model_profile: str = "gemini"
    llm_provider_id: Optional[UUID] = None
    scope: Literal["all", "volume", "book"] = "all"
    volume_node_id: Optional[UUID] = None
    use_linter_seed: bool = True
    linter_must_fix_chapter_numbers: Optional[list[int]] = None


class OutlineSnapshotRequest(BaseModel):
    label: str = "手动快照"
    note: Optional[str] = None
    scope: Literal["book", "volume"] = "book"
    volume_node_id: Optional[UUID] = None


class CommitExpandRequest(BaseModel):
    parent_node_id: str
    chapters: List[dict]
