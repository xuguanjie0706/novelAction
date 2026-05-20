"""
reader_simulation_schemas.py — 追读模拟 / 钩子检测 / 故事线分析 Pydantic 数据结构

资源边界：仅包含 Pydantic BaseModel 子类，无 DB / AI 调用，无路由。
供 reader_simulation_routes.py 和 reader_simulation_helpers.py 共同导入。
"""
from __future__ import annotations

from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class ReaderSimulationRequest(BaseModel):
    """追读模拟请求体。"""
    chapter_id: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class ReaderSimulationResult(BaseModel):
    """单章追读模拟结果。"""
    chapter_id: str
    chapter_title: str
    chapter_number: int
    will_continue: bool
    """读者是否会点下一章"""
    score: int
    """追读意愿分（1-10），10 = 不看完睡不着"""
    drop_risk: Literal["low", "medium", "high"]
    """弃文风险等级"""
    what_hooked: str
    """让读者想继续的点"""
    what_repelled: str
    """让读者犹豫的点"""
    verdict: str
    """读者视角的一句话总结"""
    hook_tail: str
    """实际送入模型的章末文本（供调试）"""


class HookCheckRequest(BaseModel):
    """章末钩子检测请求体。"""
    chapter_id: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class MatchedPromise(BaseModel):
    promise_id: str
    promise_text: str
    promise_type: str
    status: str


class HookCheckResult(BaseModel):
    """章末钩子检测结果。"""
    chapter_id: str
    chapter_title: str
    hook_text: str
    """实际章末文本"""
    hook_type: Literal["cliffhanger", "curiosity", "promise", "emotional", "revelation", "weak", "none"]
    """钩子类型"""
    hook_strength: int
    """强度 1-5（与 ChapterIndex.hook_strength 同量纲）"""
    matched_promises: List[MatchedPromise]
    """本章末尾兑现或埋下的 ReaderPromise"""
    analysis: str
    """AI 对钩子的定性分析"""
    suggestions: List[str]
    """具体改进建议（最多 3 条）"""


class StorylineGapItem(BaseModel):
    storyline_id: str
    storyline_name: str
    line_type: str
    status: str
    last_seen_chapter_number: Optional[int]
    """最后出现的章节序号（None = 从未出现）"""
    current_max_chapter: int
    """当前书稿最大章节序号"""
    gap_size: int
    """连续缺席章节数"""
    severity: Literal["warning", "critical"]


class StorylineGapsResult(BaseModel):
    gaps: List[StorylineGapItem]
    total_chapters: int
    checked_storylines: int


class ChapterAnalysisRequest(BaseModel):
    """章节综合分析请求：单次 LLM 调用，结果写入 DB，返回该章均值统计。"""
    chapter_id: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class ChapterAnalysisResult(BaseModel):
    """单次 LLM 调用返回的完整分析结果（未均值化），内部用于写库。"""
    simulation: ReaderSimulationResult
    hook: HookCheckResult


class ChapterAnalysisStats(BaseModel):
    """章节分析均值统计——汇总该章所有历史分析记录后的结果。

    Fields
    ------
    run_count       历史运行次数（越多越可信）
    avg_score       追读意愿均值（float，保留一位小数展示）
    avg_hook_strength  钩子强度均值（float）
    drop_risk       由 avg_score 推导：>=7 → low, >=5 → medium, else high
    will_continue   由 avg_score 推导：>=6 → True
    latest_*        最近一次分析的定性字段（verdict、钩子分析等）
    latest_at       最近一次分析的 ISO 时间戳
    """
    chapter_id: str
    run_count: int
    avg_score: float
    avg_hook_strength: float
    drop_risk: Literal["low", "medium", "high"]
    will_continue: bool
    # ── 最新一次定性字段（展示给作者的建议） ──
    what_hooked: str
    what_repelled: str
    verdict: str
    hook_type: str
    hook_analysis: str
    hook_suggestions: List[str]
    matched_promises: List[MatchedPromise]
    hook_tail: str
    latest_at: str  # ISO 8601
