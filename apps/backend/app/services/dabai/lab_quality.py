"""dabai 实验书架章节质检 — 规则层 + LLM 层（衔接/五拍/钩子），报告落库。

与主链路 ``quality_check``（绑定 Chapter/Project）隔离，但复用其
打分合并逻辑 ``_merge_report``，保证 DBQ-* 警告口径一致。
报告写入 ``dabai_quality_reports``，每章只保留最新一条（幂等重跑）。
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiQualityReport
from app.services.dabai.lab_draft_context import build_lab_draft_context
from app.services.dabai.lab_pre_warn import _build_lab_beat_block

# 注意：quality_check 经 draft_stream → AIService → routers.ai 存在循环 import 链，
# 必须函数内延迟导入（见 run_lab_quality / _build_lab_qc_prompt）。

logger = logging.getLogger(__name__)

LAB_QC_VERSION = "dabai-lab-qc-v1"


def _plain_content(ch: DabaiChapterOutline) -> str:
    return re.sub(r"<[^>]+>", "", ch.content or "").strip()


def _rule_report(ch: DabaiChapterOutline) -> dict:
    """规则层：零 LLM 成本的硬检查，只出 warning（lab 暂无阻断规则）。"""
    content = _plain_content(ch)
    warnings: list[dict] = []

    expected = ch.expected_words or 0
    if expected and content:
        ratio = len(content) / expected
        if ratio < 0.55 or ratio > 1.45:
            warnings.append({
                "rule_id": "DLB-01",
                "message": f"字数偏离：实际 {len(content)} 字 / 目标 {expected} 字",
            })

    witnesses = [str(w) for w in (ch.witnesses or []) if str(w).strip()]
    missing = [w for w in witnesses if w not in content]
    if witnesses and missing:
        warnings.append({
            "rule_id": "DLB-02",
            "message": f"章纲见证者未出现在正文：{'、'.join(missing[:5])}",
        })

    return {
        "status": "warning" if warnings else "ok",
        "overall_score": 100 - min(len(warnings) * 10, 30),
        "blockers": [],
        "warnings": warnings,
    }


def _build_lab_qc_prompt(
    ch: DabaiChapterOutline, *, prev_tail: str,
) -> tuple[str, str]:
    """构造 LLM 质检 (system, user)。正文取头 4500 + 尾 1200（钩子在尾部）。"""
    from app.services.dabai.quality_check import _QC_SYSTEM

    content = _plain_content(ch)
    head = content[:4500]
    tail = content[-1200:] if len(content) > 5700 else ""

    parts = [f"《第{ch.chapter_number}章 {ch.title or ''}》质检。"]
    if prev_tail.strip():
        parts.append(f"【上章结尾（本章开头应承接）】\n{prev_tail.strip()[-600:]}")
    parts.append(f"【章纲五拍要素】\n{_build_lab_beat_block(ch)}")
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


async def run_lab_quality(
    svc,
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    *,
    with_llm: bool = True,
) -> dict:
    """lab 质检入口：规则报告必出，LLM 报告可降级（llm_status 标记）。

    Args:
        svc: AIService（with_llm=False 时可传 None）。
        with_llm: False 时只跑规则（快速校验 / mock 项目用）。
    Returns:
        合并后的报告 dict（已落库）。
    """
    from app.services.dabai.quality_check import _merge_report

    rule = _rule_report(ch)

    llm_data: dict | None = None
    llm_status = "skipped"
    if with_llm:
        llm_status = "ok"
        try:
            from app.services.bootstrap.parse import parse_json
            from app.services.bootstrap.retry import call_with_retry

            ctx = build_lab_draft_context(db, project, ch)
            system, user = _build_lab_qc_prompt(ch, prev_tail=ctx.prev_tail)
            raw = await call_with_retry(
                svc, system, user, max_tokens=1400, task="dabai.quality",
            )
            llm_data = parse_json(raw)
            if not isinstance(llm_data, dict):
                llm_status = "parse_error"
                llm_data = None
        except Exception as exc:  # noqa: BLE001
            logger.warning("dabai-lab LLM 质检降级 chapter=%s: %s", ch.id, exc)
            llm_status = "error"

    report = _merge_report(rule, llm_data, llm_status)
    report["version"] = LAB_QC_VERSION
    persist_lab_quality(db, project, ch, report)
    return report


def persist_lab_quality(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    report: dict,
) -> DabaiQualityReport:
    """每章只保留最新一条报告（先删后插，幂等）。"""
    db.query(DabaiQualityReport).filter(
        DabaiQualityReport.chapter_id == ch.id,
    ).delete(synchronize_session=False)
    row = DabaiQualityReport(
        project_id=project.id,
        chapter_id=ch.id,
        chapter_number=ch.chapter_number,
        version=str(report.get("version") or LAB_QC_VERSION),
        status=str(report.get("status") or "ok"),
        overall_score=int(report.get("overall_score") or 0),
        report=report,
    )
    db.add(row)
    db.commit()
    return row
