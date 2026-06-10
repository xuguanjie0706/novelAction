"""dabai 章节质检 v2 — 规则一致性 + LLM 结构化质检（衔接 / 五拍落实 / 钩子）。

分层：
  - 规则层：沿用 ``consistency_check.check_dabai_consistency``（DBC-01 境界倒退阻断等），
    仍是唯一**阻断**来源；
  - LLM 层：低温结构化 JSON（task=dabai.quality），检查三件事：
    ① 开头是否承接上章结尾/末钩子（continuity）
    ② 五拍是否逐项落实（beats: pass/partial/miss）
    ③ 章末钩子强度（hook）
    只产生 warning 与 suggestions，不阻断；大白文取向——直白/口语不扣分，
    禁止输出「增强文采」类建议。

LLM 失败时整体降级为规则报告（llm_status=error/skipped），不阻塞写章。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Chapter, OutlineNode, Project
from app.services.dabai.consistency_check import check_dabai_consistency
from app.services.dabai.draft_prompt import build_dabai_chapter_elements_block
from app.services.dabai.draft_stream import _prev_chapter_tail
from app.services.dabai.outline_plan import resolve_chapter_plan

logger = logging.getLogger(__name__)

QC_VERSION = "dabai-qc-v2"

_QC_SYSTEM = (
    "你是番茄/七猫大白文责编，负责结构化质检。注意：大白文取向——"
    "大白话、短句、口语化、解释直白都**不扣分**；"
    "禁止提出「增强文采」「多留白」「提升文学性」类建议。只返回 JSON。"
)

_BEAT_KEYS = ("yaqu", "trigger", "yinbao", "payoff", "hook")
_BEAT_LABELS = {
    "yaqu": "憋屈铺垫",
    "trigger": "转折扳机",
    "yinbao": "引爆",
    "payoff": "爽点+见证者",
    "hook": "章末钩子",
}
_BEAT_SCORE = {"pass": 100, "partial": 60, "miss": 20}


def build_qc_prompt(
    chapter: Chapter,
    plan: OutlineNode | None,
    *,
    prev_tail: str,
) -> tuple[str, str]:
    """构造 LLM 质检 (system, user)。正文取头 4500 + 尾 1200（钩子在尾部）。"""
    import re

    content = re.sub(r"<[^>]+>", "", chapter.content or "").strip()
    head = content[:4500]
    tail = content[-1200:] if len(content) > 5700 else ""
    beat_block = build_dabai_chapter_elements_block(plan)

    parts = [f"《{chapter.title}》质检。"]
    if prev_tail.strip():
        parts.append(f"【上章结尾（本章开头应承接）】\n{prev_tail.strip()[-600:]}")
    parts.append(f"【章纲五拍要素】\n{beat_block}")
    parts.append(f"【本章正文（开头部分）】\n{head}")
    if tail:
        parts.append(f"【本章正文（结尾部分）】\n{tail}")
    parts.append(
        "逐项检查后只返回 JSON：\n"
        "{\n"
        '  "continuity_score": 0-100,  // 开头是否承接上章结尾与末钩子；无上章时给 100\n'
        '  "continuity_issue": "一句话，无问题留空",\n'
        '  "beats": {"yaqu": "pass|partial|miss", "trigger": "...", "yinbao": "...", '
        '"payoff": "...", "hook": "..."},  // 五拍是否逐项落实（payoff 须有见证者反应）\n'
        '  "beat_issues": ["未落实拍的具体问题，每条≤30字"],\n'
        '  "hook_score": 0-100,  // 章末钩子强度：能否让读者点开下一章\n'
        '  "hook_issue": "一句话，无问题留空",\n'
        '  "repetition_issue": "明显的重复铺陈/口水循环，无则留空",\n'
        '  "suggestions": ["≤3条可执行修改建议，禁止文采类"]\n'
        "}"
    )
    return _QC_SYSTEM, "\n\n".join(parts)


def _coerce_score(v: Any, default: int = 80) -> int:
    try:
        return max(0, min(100, int(float(v))))
    except (TypeError, ValueError):
        return default


def _beat_summary(beats: dict) -> tuple[int, list[str]]:
    """五拍状态 → (均分, 未落实拍的标签列表)。"""
    scores: list[int] = []
    missing: list[str] = []
    for key in _BEAT_KEYS:
        status = str(beats.get(key) or "pass").lower()
        scores.append(_BEAT_SCORE.get(status, 60))
        if status in ("partial", "miss"):
            missing.append(f"{_BEAT_LABELS[key]}（{status}）")
    return (round(sum(scores) / len(scores)) if scores else 100), missing


def _merge_report(rule: dict, llm: dict | None, llm_status: str) -> dict:
    """规则 + LLM 合并：规则 blockers 仍是唯一阻断；LLM 只追加 warning 与建议。"""
    report = dict(rule)
    report["version"] = QC_VERSION
    report["llm_status"] = llm_status
    if not isinstance(llm, dict) or llm_status != "ok":
        return report

    warnings = list(report.get("warnings") or [])
    continuity = _coerce_score(llm.get("continuity_score"))
    hook = _coerce_score(llm.get("hook_score"))
    beat_score, missing_beats = _beat_summary(llm.get("beats") or {})

    if continuity < 70:
        warnings.append({
            "rule_id": "DBQ-01",
            "message": f"开头衔接弱（{continuity}分）：{str(llm.get('continuity_issue') or '')[:80]}",
        })
    for label in missing_beats:
        warnings.append({"rule_id": "DBQ-02", "message": f"五拍未落实：{label}"})
    if hook < 60:
        warnings.append({
            "rule_id": "DBQ-03",
            "message": f"章末钩子弱（{hook}分）：{str(llm.get('hook_issue') or '')[:80]}",
        })
    rep = str(llm.get("repetition_issue") or "").strip()
    if rep:
        warnings.append({"rule_id": "DBQ-04", "message": f"重复铺陈：{rep[:80]}"})

    report["warnings"] = warnings
    report["llm"] = {
        "continuity_score": continuity,
        "continuity_issue": str(llm.get("continuity_issue") or "")[:200],
        "beats": {k: str((llm.get("beats") or {}).get(k) or "pass") for k in _BEAT_KEYS},
        "beat_issues": [str(x)[:80] for x in (llm.get("beat_issues") or [])][:5],
        "beat_score": beat_score,
        "hook_score": hook,
        "hook_issue": str(llm.get("hook_issue") or "")[:200],
        "suggestions": [str(s)[:120] for s in (llm.get("suggestions") or [])][:3],
    }

    # 综合分：规则阻断 → 保持规则给的 40；否则 衔接40% + 五拍40% + 钩子20%
    if report.get("blockers"):
        return report
    overall = round(continuity * 0.4 + beat_score * 0.4 + hook * 0.2)
    report["overall_score"] = overall
    report["status"] = "ok" if not warnings else "warning"
    return report


async def run_dabai_quality(
    svc: Any,
    db: Session,
    project: Project,
    chapter: Chapter,
    *,
    plan_node: OutlineNode | None = None,
    with_llm: bool = True,
) -> dict:
    """dabai 质检 v2 入口：规则报告必出，LLM 报告可降级。

    Args:
        with_llm: False 时只跑规则（手动「快速校验」用）。
    Returns:
        report dict（写入 ``chapter.last_quality_report`` 的最终结构）。
    """
    if not plan_node:
        plan_node = resolve_chapter_plan(db, str(project.id), chapter)
    rule = check_dabai_consistency(db, project, chapter, plan_node=plan_node)

    if not with_llm:
        return _merge_report(rule, None, "skipped")

    llm_data: dict | None = None
    llm_status = "ok"
    try:
        from app.services.bootstrap.parse import parse_json

        prev_tail = (
            _prev_chapter_tail(db, str(project.id), chapter)
            if (chapter.sort_order or 0) > 0 else ""
        )
        system, user = build_qc_prompt(chapter, plan_node, prev_tail=prev_tail)
        raw = await svc._call_with_retry(system, user, task="dabai.quality", max_tokens=1400)
        llm_data = parse_json(raw)
        if not isinstance(llm_data, dict):
            llm_status = "parse_error"
            llm_data = None
    except Exception as exc:
        logger.warning("dabai LLM 质检降级 chapter=%s: %s", chapter.id, exc)
        llm_status = "error"

    return _merge_report(rule, llm_data, llm_status)
