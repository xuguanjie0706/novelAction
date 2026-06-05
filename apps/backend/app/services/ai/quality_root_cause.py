"""质检根因台账 —— 分析层（编排薄壳 + LLM 归因）。

职责
----
拿收集层落库的 pending 低分项，单次批量调 LLM 判定每项根因（落在管线哪一层），
写回 ``root_cause_category`` / ``root_cause_detail`` / ``code_fix_suggestion`` / ``evidence``。
``collect_and_analyze`` 是给质检路由调用的一站式入口，全程 best-effort，绝不让质检主流程失败。

prompt 见 ``prompts/quality_root_cause_prompt.py``；收集见 ``quality_root_cause_collect.py``。
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Chapter, LlmCallLog, Project, QualityRootCauseLog
from app.services.bootstrap.parse import parse_json
from app.services.ai.quality_root_cause_collect import extract_low_items, record_low_items
from app.services.ai.prompts.quality_root_cause_prompt import (
    CATEGORIES,
    CATEGORY_FIX_HINTS,
    ROOT_CAUSE_SYSTEM,
    build_root_cause_prompt,
)

logger = logging.getLogger(__name__)


def load_draft_context_note(db: Session, project_id: str, chapter: Chapter) -> str:
    """best-effort 说明写章上下文是否可考据（不强依赖 JSON 字段精确匹配）。"""
    try:
        has_draft = (
            db.query(LlmCallLog.id)
            .filter(LlmCallLog.mode.ilike("%draft%"))
            .order_by(LlmCallLog.created_at.desc())
            .first()
        )
    except Exception:
        has_draft = None
    if has_draft:
        return (
            "已找到写章 LLM 调用记录。下方「系统当前掌握的设定」即写章时同一数据源；"
            "若其中已含被违反的事实，则更可能是注入了被忽略（context_ignored）或缺硬约束（prompt_constraint_gap）。"
        )
    return "未检索到明确的写章调用记录；请主要依据「系统当前掌握的设定」与正文摘录判断信息是否本可注入。"


async def analyze_root_causes(
    ai,
    db: Session,
    chapter: Chapter,
    rows: list[QualityRootCauseLog],
    system_knowledge_brief: str,
    draft_context_note: str,
) -> int:
    """对 pending 行批量归因并写回。返回成功分析的条数。"""
    pending = [r for r in rows if r.analysis_status == "pending"]
    if not pending:
        return 0

    items = [
        {
            "idx": i,
            "item_kind": r.item_kind,
            "dimension": r.dimension,
            "score": r.score,
            "problem_summary": r.problem_summary,
        }
        for i, r in enumerate(pending)
    ]
    excerpt = ai._clip_context(ai._plain_text(chapter.content or ""), 1200, 8000)
    prompt = build_root_cause_prompt(
        chapter_title=chapter.title or "",
        chapter_excerpt=excerpt or "（正文为空）",
        system_knowledge_brief=system_knowledge_brief or "（无）",
        draft_context_note=draft_context_note,
        items=items,
    )

    try:
        resp = await ai._call_ai(
            ROOT_CAUSE_SYSTEM,
            prompt,
            context={"operation": "quality_root_cause", "chapter_title": chapter.title},
            task="quality.root_cause",
        )
        data = parse_json(resp)
    except Exception as exc:  # noqa: BLE001
        logger.warning("quality_root_cause analyze failed: %s", exc)
        for r in pending:
            r.analysis_status = "failed"
        db.flush()
        return 0

    by_idx: dict[int, dict] = {}
    if isinstance(data, dict):
        for res in data.get("results") or []:
            if isinstance(res, dict) and isinstance(res.get("idx"), int):
                by_idx[res["idx"]] = res

    ok = 0
    for i, r in enumerate(pending):
        res = by_idx.get(i)
        cat = str((res or {}).get("root_cause_category") or "unknown").strip()
        if cat not in CATEGORIES:
            cat = "unknown"
        r.root_cause_category = cat
        r.root_cause_detail = str((res or {}).get("root_cause_detail") or "").strip()[:1000]
        llm_fix = str((res or {}).get("code_fix_suggestion") or "").strip()[:1000]
        static_hint = CATEGORY_FIX_HINTS.get(cat, "")
        r.code_fix_suggestion = llm_fix or static_hint
        r.evidence = {
            "category_desc": CATEGORIES.get(cat, ""),
            "static_fix_hint": static_hint,
            "had_llm_result": res is not None,
        }
        r.analysis_status = "analyzed"
        ok += 1
    db.flush()
    return ok


async def collect_and_analyze(
    ai,
    db: Session,
    project: Project,
    chapter: Chapter,
    report: dict,
    system_knowledge_brief: str,
) -> dict:
    """质检路由调用的一站式入口：提取低分项 → 落库 → LLM 归因。

    全程 best-effort：任何异常只记日志并返回统计，绝不让质检主流程失败。
    """
    summary = {"run_id": "", "collected": 0, "analyzed": 0}
    try:
        items = extract_low_items(report)
        if not items:
            return summary
        run_id = str(uuid.uuid4())
        summary["run_id"] = run_id
        rows = record_low_items(db, str(project.id), chapter, items, run_id)
        summary["collected"] = len(rows)
        note = load_draft_context_note(db, str(project.id), chapter)
        summary["analyzed"] = await analyze_root_causes(
            ai, db, chapter, rows, system_knowledge_brief, note
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("collect_and_analyze root cause failed: %s", exc)
    return summary


def build_system_knowledge_brief(
    character_states: Optional[list[str]] = None,
    power_systems_summary: Optional[list[str]] = None,
    continuity_context: str = "",
    storylines_context: Optional[list[str]] = None,
) -> str:
    """把质检路由已组装好的上下文拼成给归因器的「系统当前掌握」简报。"""
    parts: list[str] = []
    if character_states:
        parts.append("【人物当前状态】\n" + "\n".join(f"- {c}" for c in character_states[:60]))
    if power_systems_summary:
        ps = [p for p in power_systems_summary if p and p.strip()]
        if ps:
            parts.append("【力量体系/境界规则】\n" + "\n".join(ps)[:4000])
    if storylines_context:
        parts.append("【活跃故事线】\n" + "\n".join(f"- {s}" for s in storylines_context[:30]))
    if continuity_context:
        parts.append("【连续性账本】\n" + continuity_context[:4000])
    return "\n\n".join(parts)
