"""
追读模拟 · 章末钩子检测 · 故事线悬空检测 · 章节综合分析

端点清单
--------
- reader-simulation      章末追读模拟：AI 扮演目标读者，判断读完本章是否会点下一章。
- hook-check             章末钩子检测：提取章尾 ~300 字，评估钩子类型/强度，比对开放承诺。
- storyline-gaps         故事线悬空检测：纯逻辑，无 AI 调用，找出 N 章以上未出现的活跃故事线。
- chapter-analysis       【推荐入口】单次 LLM 调用，结果写入 chapter_analysis_records 表，返回该章均值。
- chapter-analysis-stats 读取各章分析记录均值，无 AI 调用，供页面加载时批量拉取。
"""

import json
import re
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from sqlalchemy import func as sql_func

from app.database import get_db
from app.models import (
    Chapter,
    ChapterAnalysisRecord,
    ChapterIndex,
    OutlineNode,
    Project,
    ReaderPromise,
    StoryLine,
)
from app.routers.ai.text_utils import plain_text, truncate
from app.services.ai_service import AIService
from app.services.generation_service import _parse_json

router = APIRouter()

# ── 常量 ─────────────────────────────────────────────────────────────────────

#: 故事线悬空阈值：活跃故事线连续 N 章未出现视为警告，2N 章视为严重
_STORYLINE_GAP_WARN = 8
_STORYLINE_GAP_CRITICAL = 16

#: 章末钩子截取字符数（纯文本）
_HOOK_TAIL_CHARS = 300


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

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


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _extract_hook_tail(chapter: Chapter, chars: int = _HOOK_TAIL_CHARS) -> str:
    """从章节正文提取末尾纯文本。

    Args:
        chapter: Chapter ORM 对象，从 content（HTML/Markdown 混合）提取。
        chars: 保留字符数。

    Returns:
        末尾纯文本，最多 `chars` 字。
    """
    raw = plain_text(chapter.content or "")
    return raw[-chars:].strip() if len(raw) > chars else raw.strip()


def _get_chapter_summary(chapter: Chapter, chapter_index: Optional[ChapterIndex]) -> str:
    """组装章节摘要，用于追读模拟的上下文。

    Args:
        chapter: 章节 ORM 对象。
        chapter_index: 可选的章节索引（已有则提供更准确的剧情摘要）。

    Returns:
        多行文本，描述本章核心事件与状态。
    """
    parts: list[str] = []
    if chapter_index:
        events = chapter_index.core_events or []
        event_strs = []
        for e in events[:5]:
            if isinstance(e, dict):
                event_strs.append(e.get("event") or e.get("description") or str(e))
            else:
                event_strs.append(str(e))
        if event_strs:
            parts.append("本章核心事件：" + "；".join(event_strs))
        if chapter_index.ending_hook:
            parts.append(f"索引记录的章末钩子：{chapter_index.ending_hook}")
    else:
        # 降级：从正文截取前 400 字作为摘要
        raw = plain_text(chapter.content or "")
        parts.append("章节正文（节选）：" + raw[:400])
    return "\n".join(parts) if parts else "（无额外摘要）"


# ── 端点 ──────────────────────────────────────────────────────────────────────

@router.post("/reader-simulation", response_model=ReaderSimulationResult)
async def reader_simulation(
    project_id: str,
    req: ReaderSimulationRequest,
    db: Session = Depends(get_db),
):
    """
    章末追读模拟。

    AI 扮演本书目标读者群（由 Project.extra.positioning 描述），
    读完本章后判断：是否会立即点下一章？并给出详细理由。

    返回结果可存入前端节奏地图，供作者纵览各章留存风险。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id,
        Chapter.project_id == project_id,
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    chapter_index = db.query(ChapterIndex).filter(
        ChapterIndex.chapter_id == req.chapter_id
    ).first()

    # ── 组装上下文 ──
    positioning = {}
    if isinstance(project.extra, dict):
        positioning = project.extra.get("positioning") or {}

    target_audience = positioning.get("target_audience") or "网文核心读者（18-35岁，偏好爽感流）"
    tropes = positioning.get("tropes") or []
    tropes_str = "、".join(tropes[:5]) if isinstance(tropes, list) else str(tropes)
    face_slap = positioning.get("face_slap_pattern") or "无特定设定"
    pace_type = positioning.get("pace_type") or "标准节奏"

    hook_tail = _extract_hook_tail(chapter)
    chapter_summary = _get_chapter_summary(chapter, chapter_index)
    chapter_num = chapter_index.chapter_number if chapter_index else (chapter.sort_order + 1)

    system_prompt = (
        "你是一位经验丰富的网文编辑，现在需要模拟本书目标读者的追读决策。\n"
        "你的判断必须基于：读者体验、章末吸引力、情绪满足度，而非文学价值。\n"
        "只返回 JSON，不要有任何额外文本。"
    )

    user_prompt = f"""【作品信息】
书名：{project.title}
类型：{getattr(project, 'genre', '') or '未知'}
目标读者：{target_audience}
常用套路：{tropes_str or '无'}
打脸节奏：{face_slap}
节奏类型：{pace_type}

【本章信息（第{chapter_num}章：{chapter.title}）】
字数：{chapter.word_count or 0}字
{chapter_summary}

【章末实际文本（最后~300字）】
{hook_tail}

【任务】
作为以上目标读者，你刚刚读完这一章。请判断：你会立刻点下一章吗？

返回以下 JSON（所有字段必填）：
{{
  "will_continue": true/false,
  "score": 整数1-10（10=不看完睡不着，1=直接弃书）,
  "drop_risk": "low"/"medium"/"high",
  "what_hooked": "让你想继续看的点（30字内）",
  "what_repelled": "让你犹豫或反感的点（30字内，无则填'无'）",
  "verdict": "以读者口吻说一句话（50字内）"
}}"""

    ai = AIService(
        profile=req.model_profile,
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    raw = await ai._call_ai(
        system=system_prompt,
        prompt=user_prompt,
        max_tokens=512,
        task="quality.check",  # 稳定 JSON，用低温度档位
    )

    try:
        data = _parse_json(raw)
    except Exception:
        raise HTTPException(500, f"AI 返回格式异常：{raw[:200]}")

    score = int(data.get("score") or 5)
    will_continue = bool(data.get("will_continue", score >= 6))
    drop_risk_val = data.get("drop_risk") or ("low" if score >= 7 else "medium" if score >= 4 else "high")
    if drop_risk_val not in ("low", "medium", "high"):
        drop_risk_val = "medium"

    return ReaderSimulationResult(
        chapter_id=str(chapter.id),
        chapter_title=chapter.title,
        chapter_number=chapter_num,
        will_continue=will_continue,
        score=score,
        drop_risk=drop_risk_val,
        what_hooked=data.get("what_hooked") or "",
        what_repelled=data.get("what_repelled") or "",
        verdict=data.get("verdict") or "",
        hook_tail=hook_tail,
    )


@router.post("/hook-check", response_model=HookCheckResult)
async def hook_check(
    project_id: str,
    req: HookCheckRequest,
    db: Session = Depends(get_db),
):
    """
    章末钩子质量检测。

    提取章尾约 300 字的纯文本，AI 分类钩子类型（悬念 / 好奇 / 承诺 / 情感 / 反转 / 弱 / 无），
    并比对本项目的开放 ReaderPromise，判断是否有承诺在此章被埋下或兑现。

    建议在「复盘」流程后调用，此时 ChapterIndex 已存在，结果更准确。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id,
        Chapter.project_id == project_id,
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    # 开放的读者承诺列表（open 状态，与本章可能有关）
    open_promises = db.query(ReaderPromise).filter(
        ReaderPromise.project_id == project_id,
        ReaderPromise.status == "open",
    ).order_by(ReaderPromise.source_chapter_number.asc()).limit(20).all()

    hook_tail = _extract_hook_tail(chapter)

    promises_ctx = ""
    if open_promises:
        lines = [
            f"- [{p.promise_type}] {p.promise_text}（来源：第{p.source_chapter_number or '?'}章）"
            for p in open_promises[:10]
        ]
        promises_ctx = "\n当前开放的读者承诺：\n" + "\n".join(lines)

    system_prompt = (
        "你是资深网文编辑，专注于章末钩子分析。"
        "只返回 JSON，不要有任何额外文本。"
    )

    hook_type_desc = (
        "cliffhanger=生死悬念, curiosity=信息悬念/好奇心, "
        "promise=明确预告下一章内容, emotional=情感高潮/共鸣, "
        "revelation=反转/真相揭露, weak=钩子存在但力度不足, none=无明显钩子"
    )

    user_prompt = f"""【章节】第{chapter.sort_order + 1}章：{chapter.title}
{promises_ctx}

【章末文本（最后~300字）】
{hook_tail}

【任务】分析这段章末文本的钩子质量。

返回 JSON：
{{
  "hook_type": "{hook_type_desc} 中选一个英文 key",
  "hook_strength": 整数1-5（5=极强悬念，1=几乎没有），
  "analysis": "对钩子的定性分析（80字内）",
  "matched_promise_texts": ["与开放承诺列表中匹配的承诺原文（完全匹配）"],
  "suggestions": ["改进建议1（50字内）", "改进建议2（可选）", "改进建议3（可选）"]
}}
若无开放承诺匹配，matched_promise_texts 为空数组。suggestions 最多 3 条。"""

    ai = AIService(
        profile=req.model_profile,
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    raw = await ai._call_ai(
        system=system_prompt,
        prompt=user_prompt,
        max_tokens=600,
        task="quality.check",
    )

    try:
        data = _parse_json(raw)
    except Exception:
        raise HTTPException(500, f"AI 返回格式异常：{raw[:200]}")

    # 匹配返回的承诺文本到数据库记录
    matched_texts: list[str] = data.get("matched_promise_texts") or []
    matched: list[MatchedPromise] = []
    for p in open_promises:
        for mt in matched_texts:
            if mt and (mt in p.promise_text or p.promise_text in mt):
                matched.append(MatchedPromise(
                    promise_id=str(p.id),
                    promise_text=p.promise_text,
                    promise_type=p.promise_type,
                    status=p.status,
                ))
                break

    valid_types = {"cliffhanger", "curiosity", "promise", "emotional", "revelation", "weak", "none"}
    hook_type = data.get("hook_type") or "weak"
    if hook_type not in valid_types:
        hook_type = "weak"

    suggestions_raw = data.get("suggestions") or []
    suggestions = [str(s) for s in suggestions_raw[:3] if s]

    return HookCheckResult(
        chapter_id=str(chapter.id),
        chapter_title=chapter.title,
        hook_text=hook_tail,
        hook_type=hook_type,
        hook_strength=max(1, min(5, int(data.get("hook_strength") or 2))),
        matched_promises=matched,
        analysis=data.get("analysis") or "",
        suggestions=suggestions,
    )


@router.get("/storyline-gaps", response_model=StorylineGapsResult)
def storyline_gaps(
    project_id: str,
    gap_threshold: int = _STORYLINE_GAP_WARN,
    db: Session = Depends(get_db),
):
    """
    故事线悬空检测（无 AI 调用，纯逻辑）。

    逻辑：
    1. 取所有「active/climax」状态的故事线。
    2. 对每条故事线，查找引用了该 storyline_id 的 chapter_plan OutlineNode，
       并通过 outline_node → chapter 拿到最大 sort_order（即最后出现章节）。
    3. 当前书稿最大章节号 - 最后出现章节号 > gap_threshold，标记悬空警告。

    Args:
        gap_threshold: 连续缺席章节阈值，默认 8。超过 2 倍（16 章）升级为 critical。
    """
    # 当前书稿所有章节的最大 sort_order（1-indexed chapter number）
    all_chapters = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id)
        .order_by(Chapter.sort_order.asc())
        .all()
    )
    if not all_chapters:
        return StorylineGapsResult(gaps=[], total_chapters=0, checked_storylines=0)

    max_sort_order = max(c.sort_order for c in all_chapters)
    # sort_order 从 0 开始时 +1 得到章节序号；若业务里已是 1-indexed 则直接用
    total_chapters = max_sort_order + 1

    # 活跃故事线
    active_storylines = (
        db.query(StoryLine)
        .filter(
            StoryLine.project_id == project_id,
            StoryLine.status.in_(["active", "climax"]),
        )
        .all()
    )

    # chapter_plan OutlineNode（带 storyline_ids 字段）→ 关联的 Chapter sort_order
    # 通过 OutlineNode.chapter 反向关系拿 sort_order
    chapter_plan_nodes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "chapter_plan",
        )
        .all()
    )

    # 构建：storyline_id → 出现过的章节 sort_order 列表
    storyline_appearances: dict[str, list[int]] = {}
    for node in chapter_plan_nodes:
        sl_ids: list = node.storyline_ids or []
        if not sl_ids:
            continue
        # 找关联章节的 sort_order
        ch = node.chapter  # OutlineNode → Chapter（一对一）
        if ch is None:
            continue
        for sl_id in sl_ids:
            sl_str = str(sl_id)
            storyline_appearances.setdefault(sl_str, []).append(ch.sort_order)

    gaps: list[StorylineGapItem] = []
    for sl in active_storylines:
        sl_id = str(sl.id)
        appearances = storyline_appearances.get(sl_id, [])

        if appearances:
            last_sort_order = max(appearances)
            last_chapter_num = last_sort_order + 1  # sort_order(0-based) → chapter number(1-based)
            gap = total_chapters - last_chapter_num
        else:
            last_chapter_num = None
            gap = total_chapters  # 从未出现

        if gap < gap_threshold:
            continue  # 未达阈值，跳过

        severity: Literal["warning", "critical"] = (
            "critical" if gap >= gap_threshold * 2 else "warning"
        )
        gaps.append(StorylineGapItem(
            storyline_id=sl_id,
            storyline_name=sl.name,
            line_type=sl.line_type or "main",
            status=sl.status,
            last_seen_chapter_number=last_chapter_num,
            current_max_chapter=total_chapters,
            gap_size=gap,
            severity=severity,
        ))

    gaps.sort(key=lambda g: g.gap_size, reverse=True)

    return StorylineGapsResult(
        gaps=gaps,
        total_chapters=total_chapters,
        checked_storylines=len(active_storylines),
    )


# ── 综合分析（写库 + 均值统计） ───────────────────────────────────────────────

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


def _derive_drop_risk(avg_score: float) -> Literal["low", "medium", "high"]:
    """由均值推导弃文风险等级。"""
    if avg_score >= 7:
        return "low"
    if avg_score >= 5:
        return "medium"
    return "high"


def _build_stats_from_records(
    chapter_id: str,
    records: list[ChapterAnalysisRecord],
) -> ChapterAnalysisStats:
    """从该章所有历史记录构造均值统计对象。

    Args:
        chapter_id: 章节 ID（str）。
        records: 按 created_at 升序排列的 ChapterAnalysisRecord 列表（非空）。

    Returns:
        ChapterAnalysisStats，avg_score/avg_hook_strength 取所有记录均值，
        定性字段取最新记录。

    Raises:
        ValueError: records 为空时抛出。
    """
    if not records:
        raise ValueError("records must not be empty")

    n = len(records)
    avg_score = sum(r.score for r in records) / n
    avg_hook_strength = sum(r.hook_strength for r in records) / n

    latest = records[-1]  # 已按 created_at asc 排列，最后一条即最新

    matched: list[MatchedPromise] = []
    for mp in (latest.matched_promises_json or []):
        if isinstance(mp, dict):
            matched.append(MatchedPromise(
                promise_id=mp.get("promise_id", ""),
                promise_text=mp.get("promise_text", ""),
                promise_type=mp.get("promise_type", ""),
                status=mp.get("status", "open"),
            ))

    latest_at = latest.created_at.isoformat() if latest.created_at else ""

    return ChapterAnalysisStats(
        chapter_id=chapter_id,
        run_count=n,
        avg_score=round(avg_score, 1),
        avg_hook_strength=round(avg_hook_strength, 1),
        drop_risk=_derive_drop_risk(avg_score),
        will_continue=avg_score >= 6,
        what_hooked=latest.what_hooked or "",
        what_repelled=latest.what_repelled or "",
        verdict=latest.verdict or "",
        hook_type=latest.hook_type or "weak",
        hook_analysis=latest.hook_analysis or "",
        hook_suggestions=latest.hook_suggestions or [],
        matched_promises=matched,
        hook_tail=latest.hook_tail or "",
        latest_at=latest_at,
    )


async def _single_shot_analysis(
    project_id: str,
    chapter: Chapter,
    project: Project,
    chapter_index: "ChapterIndex | None",
    open_promises: list,
    model_profile: str,
    llm_provider_id: "UUID | None",
    db: Session,
) -> ChapterAnalysisResult:
    """
    单次 LLM 调用完成追读模拟 + 钩子检测。

    设计原则
    --------
    - 上下文只组装一次，prompt 描述两个并列任务，要求模型返回带两个顶层 key 的 JSON。
    - 两个维度共享同一视角（网文编辑/目标读者），内部结论天然一致。
    - 解析失败时抛出 HTTPException，不做静默降级，让调用方决定重试策略。

    Args:
        project_id: 项目 ID。
        chapter: 章节 ORM 对象。
        project: 项目 ORM 对象。
        chapter_index: 可选章节索引，提供核心事件摘要。
        open_promises: 本项目开放状态的 ReaderPromise 列表。
        model_profile: 模型线路（local/gemini）。
        llm_provider_id: 可选远程 provider UUID。
        db: 数据库 session。

    Returns:
        ChapterAnalysisResult，包含 simulation 与 hook 两个完整子结构。
    """
    # ── 组装上下文 ──────────────────────────────────────────────────────────────
    positioning: dict = {}
    if isinstance(project.extra, dict):
        positioning = project.extra.get("positioning") or {}

    target_audience = positioning.get("target_audience") or "网文核心读者（18-35岁，偏好爽感流）"
    tropes = positioning.get("tropes") or []
    tropes_str = "、".join(tropes[:5]) if isinstance(tropes, list) else str(tropes)
    face_slap = positioning.get("face_slap_pattern") or "无特定设定"
    pace_type = positioning.get("pace_type") or "标准节奏"

    hook_tail = _extract_hook_tail(chapter)
    chapter_summary = _get_chapter_summary(chapter, chapter_index)
    chapter_num = chapter_index.chapter_number if chapter_index else (chapter.sort_order + 1)

    promises_ctx = ""
    if open_promises:
        lines = [
            f"- [{p.promise_type}] {p.promise_text}（来源：第{p.source_chapter_number or '?'}章）"
            for p in open_promises[:10]
        ]
        promises_ctx = "\n【开放中的读者承诺（供钩子匹配参考）】\n" + "\n".join(lines)

    hook_type_desc = (
        "cliffhanger=生死悬念, curiosity=信息悬念/好奇心, "
        "promise=明确预告下一章, emotional=情感高潮/共鸣, "
        "revelation=反转/真相揭露, weak=钩子力度不足, none=无明显钩子"
    )

    # ── 单次 Prompt ─────────────────────────────────────────────────────────────
    system_prompt = (
        "你是一位资深网文编辑，同时扮演两个角色：\n"
        "① 目标读者：基于爽感/追读体验做出真实的留存判断；\n"
        "② 章末钩子专家：对章末文字做结构性分析。\n"
        "只返回 JSON，不输出任何其他内容。"
    )

    user_prompt = f"""【作品信息】
书名：{project.title}
类型：{getattr(project, 'genre', '') or '未知'}
目标读者：{target_audience}
常用套路：{tropes_str or '无'}
打脸节奏：{face_slap}
节奏类型：{pace_type}

【本章（第{chapter_num}章：{chapter.title}，{chapter.word_count or 0}字）】
{chapter_summary}
{promises_ctx}

【章末文本（最后~300字）】
{hook_tail}

【任务】请以上述两个角色分别分析，返回以下完整 JSON（所有字段必填）：
{{
  "simulation": {{
    "will_continue": true或false,
    "score": 整数1-10（10=不看完睡不着，1=直接弃书）,
    "drop_risk": "low"或"medium"或"high",
    "what_hooked": "吸引读者继续看的点（30字内）",
    "what_repelled": "让读者犹豫或反感的点（30字内，无则填'无'）",
    "verdict": "以读者口吻说一句话（50字内）"
  }},
  "hook": {{
    "hook_type": "{hook_type_desc}中选一个英文key",
    "hook_strength": 整数1-5（5=极强，1=几乎没有）,
    "analysis": "对钩子的定性分析（80字内）",
    "matched_promise_texts": ["与开放承诺列表完全匹配的承诺原文"],
    "suggestions": ["改进建议1（50字内）", "改进建议2（可选）", "改进建议3（可选）"]
  }}
}}
matched_promise_texts 无匹配则为空数组；suggestions 最多3条。"""

    ai = AIService(
        profile=model_profile,
        db=db,
        llm_provider_id=llm_provider_id,
    )
    raw = await ai._call_ai(
        system=system_prompt,
        prompt=user_prompt,
        max_tokens=900,
        task="quality.check",  # 稳定 JSON，低温度档位
    )

    try:
        data = _parse_json(raw)
    except Exception:
        raise HTTPException(500, f"AI 返回格式异常：{raw[:300]}")

    # ── 解析 simulation ─────────────────────────────────────────────────────────
    sim_data: dict = data.get("simulation") or {}
    score = max(1, min(10, int(sim_data.get("score") or 5)))
    drop_risk_raw = sim_data.get("drop_risk") or (
        "low" if score >= 7 else "medium" if score >= 4 else "high"
    )
    drop_risk: Literal["low", "medium", "high"] = (
        drop_risk_raw if drop_risk_raw in ("low", "medium", "high") else "medium"
    )
    simulation = ReaderSimulationResult(
        chapter_id=str(chapter.id),
        chapter_title=chapter.title,
        chapter_number=chapter_num,
        will_continue=bool(sim_data.get("will_continue", score >= 6)),
        score=score,
        drop_risk=drop_risk,
        what_hooked=sim_data.get("what_hooked") or "",
        what_repelled=sim_data.get("what_repelled") or "",
        verdict=sim_data.get("verdict") or "",
        hook_tail=hook_tail,
    )

    # ── 解析 hook ───────────────────────────────────────────────────────────────
    hook_data: dict = data.get("hook") or {}
    valid_hook_types = {"cliffhanger", "curiosity", "promise", "emotional", "revelation", "weak", "none"}
    hook_type = hook_data.get("hook_type") or "weak"
    if hook_type not in valid_hook_types:
        hook_type = "weak"

    matched_texts: list[str] = hook_data.get("matched_promise_texts") or []
    matched: list[MatchedPromise] = []
    for p in open_promises:
        for mt in matched_texts:
            if mt and (mt in p.promise_text or p.promise_text in mt):
                matched.append(MatchedPromise(
                    promise_id=str(p.id),
                    promise_text=p.promise_text,
                    promise_type=p.promise_type,
                    status=p.status,
                ))
                break

    suggestions_raw = hook_data.get("suggestions") or []
    hook = HookCheckResult(
        chapter_id=str(chapter.id),
        chapter_title=chapter.title,
        hook_text=hook_tail,
        hook_type=hook_type,
        hook_strength=max(1, min(5, int(hook_data.get("hook_strength") or 2))),
        matched_promises=matched,
        analysis=hook_data.get("analysis") or "",
        suggestions=[str(s) for s in suggestions_raw[:3] if s],
    )

    return ChapterAnalysisResult(simulation=simulation, hook=hook)


@router.post("/chapter-analysis", response_model=ChapterAnalysisStats)
async def chapter_analysis(
    project_id: str,
    req: ChapterAnalysisRequest,
    db: Session = Depends(get_db),
):
    """
    章节综合分析（推荐入口）。

    单次 LLM 调用完成追读模拟 + 钩子检测，将结果写入 chapter_analysis_records，
    再返回该章**所有历史记录的均值统计**（ChapterAnalysisStats）。
    多次运行同一章节可获得更稳定的评估。

    Args:
        project_id: 项目 ID（路径参数）。
        req: 包含 chapter_id、model_profile、llm_provider_id 的请求体。

    Returns:
        ChapterAnalysisStats，含 run_count、avg_score、avg_hook_strength 及最新定性分析。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id,
        Chapter.project_id == project_id,
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    chapter_index = db.query(ChapterIndex).filter(
        ChapterIndex.chapter_id == req.chapter_id
    ).first()

    open_promises = db.query(ReaderPromise).filter(
        ReaderPromise.project_id == project_id,
        ReaderPromise.status == "open",
    ).order_by(ReaderPromise.source_chapter_number.asc()).limit(20).all()

    # ── AI 单次调用 ──────────────────────────────────────────────────────────
    result: ChapterAnalysisResult = await _single_shot_analysis(
        project_id=project_id,
        chapter=chapter,
        project=project,
        chapter_index=chapter_index,
        open_promises=open_promises,
        model_profile=req.model_profile,
        llm_provider_id=req.llm_provider_id,
        db=db,
    )

    # ── 写入历史记录 ─────────────────────────────────────────────────────────
    sim = result.simulation
    hook = result.hook
    record = ChapterAnalysisRecord(
        project_id=project_id,
        chapter_id=req.chapter_id,
        # simulation
        score=sim.score,
        will_continue=sim.will_continue,
        drop_risk=sim.drop_risk,
        what_hooked=sim.what_hooked,
        what_repelled=sim.what_repelled,
        verdict=sim.verdict,
        hook_tail=sim.hook_tail,
        # hook
        hook_type=hook.hook_type,
        hook_strength=hook.hook_strength,
        hook_analysis=hook.analysis,
        hook_suggestions=hook.suggestions,
        matched_promises_json=[
            {
                "promise_id": p.promise_id,
                "promise_text": p.promise_text,
                "promise_type": p.promise_type,
                "status": p.status,
            }
            for p in hook.matched_promises
        ],
    )
    db.add(record)
    db.commit()

    # ── 重新查询本章所有记录，构造均值统计 ───────────────────────────────────
    records = (
        db.query(ChapterAnalysisRecord)
        .filter(
            ChapterAnalysisRecord.chapter_id == req.chapter_id,
            ChapterAnalysisRecord.project_id == project_id,
        )
        .order_by(ChapterAnalysisRecord.created_at.asc())
        .all()
    )
    return _build_stats_from_records(str(req.chapter_id), records)


@router.get("/chapter-analysis-stats", response_model=List[ChapterAnalysisStats])
def chapter_analysis_stats(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    批量读取项目所有章节的分析均值统计（无 AI 调用）。

    供节奏地图页面在加载时一次性拉取所有已分析章节的历史均值，
    从而在刷新后仍能恢复曲线与详情展示。

    Args:
        project_id: 项目 ID（路径参数）。

    Returns:
        List[ChapterAnalysisStats]，仅包含有记录的章节（未分析章节不出现）。
    """
    records_all = (
        db.query(ChapterAnalysisRecord)
        .filter(ChapterAnalysisRecord.project_id == project_id)
        .order_by(
            ChapterAnalysisRecord.chapter_id.asc(),
            ChapterAnalysisRecord.created_at.asc(),
        )
        .all()
    )

    # 按 chapter_id 分组
    groups: dict[str, list[ChapterAnalysisRecord]] = {}
    for r in records_all:
        cid = str(r.chapter_id)
        groups.setdefault(cid, []).append(r)

    return [_build_stats_from_records(cid, recs) for cid, recs in groups.items()]
