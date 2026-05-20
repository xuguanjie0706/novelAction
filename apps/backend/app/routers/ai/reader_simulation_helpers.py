"""
reader_simulation_helpers.py — 追读模拟辅助函数

资源边界：
  - 纯辅助，无路由装饰器，无 FastAPI 依赖。
  - 供 reader_simulation_routes.py 调用。

包含函数：
  - _extract_hook_tail         — 提取章末纯文本
  - _get_chapter_summary       — 组装章节上下文摘要
  - _derive_drop_risk          — 由均值推导弃文风险
  - _build_stats_from_records  — 从历史记录构造均值统计
  - _single_shot_analysis      — 单次 LLM 调用：追读模拟 + 钩子检测
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Chapter, ChapterAnalysisRecord, ChapterIndex, Project, ReaderPromise
from app.routers.ai.reader_simulation_schemas import (
    ChapterAnalysisResult,
    ChapterAnalysisStats,
    HookCheckResult,
    MatchedPromise,
    ReaderSimulationResult,
)
from app.routers.ai.text_utils import plain_text
from app.services.ai_service import AIService
from app.services.generation_service import _parse_json

#: 章末钩子截取字符数（纯文本）
_HOOK_TAIL_CHARS = 300


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


def _get_chapter_summary(chapter: Chapter, chapter_index: ChapterIndex | None) -> str:
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
    chapter_index: ChapterIndex | None,
    open_promises: list,
    model_profile: str,
    llm_provider_id: UUID | None,
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
