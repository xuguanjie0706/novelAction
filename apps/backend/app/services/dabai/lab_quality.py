"""dabai 实验书架章节质检 — 规则层 + LLM 层（衔接/五拍/钩子），报告落库。

与主链路 ``quality_check``（绑定 Chapter/Project）隔离，但复用其
打分合并逻辑 ``_merge_report``，保证 DBQ-* 警告口径一致。
报告追加写入 ``dabai_quality_reports``（保留历史，供后台回归）。
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiQualityReport
from app.services.dabai.lab_draft_context import LabDraftContext, build_lab_draft_context
from dabai.first_chapter_opening import (
    OPENING_CLICHE_RULE_ID,
    prose_opening_cliche_hit,
    skip_ch1_cliche_lint,
    witness_stems,
)
from app.services.dabai.lab_qc_critical import run_critical_rule_checks
from app.services.dabai.lab_phrase_guard import (
    build_phrase_guard_block,
    check_chapter_phrase_violations,
)
from app.services.dabai.lab_qc_prompt import build_lab_qc_prompt
from app.services.dabai.lab_chapter_boundary import collect_future_cast_names
from app.services.dabai.lab_prompt_shared import (
    has_location_gap,
    needs_location_bridge,
    opening_continues_prev_tail,
)

# 注意：quality_check 经 draft_stream → AIService → routers.ai 存在循环 import 链，
# 必须函数内延迟导入（见 run_lab_quality / _build_lab_qc_prompt）。

logger = logging.getLogger(__name__)

LAB_QC_VERSION = "dabai-lab-qc-v4"

# 见证者群体类同义词组（DLB-02 语义匹配；禁止在此硬编码具体书的人名/家族名）
# 章纲词与正文词落在同一组即视为出现（如章纲「围观家奴」↔ 正文「家仆」）
_WITNESS_GROUP_SETS: tuple[tuple[str, ...], ...] = (
    ("家奴", "家仆", "仆人", "仆从", "随从", "杂役", "下人"),
    ("弟子", "族人", "子弟", "门人"),
    ("围观", "众人", "人群", "惊呼"),
    ("狗腿子", "跟班", "护卫", "打手"),
    ("长老", "执事", "管事"),
)


def _witness_in_content(witness: str, content: str) -> bool:
    """见证者是否在正文中出现（全称/去括号/「的」分段/群体词干，全部规则派生）。"""
    w = witness.strip()
    if not w:
        return False
    if w in content:
        return True
    for stem in witness_stems(w):
        if stem and stem in content:
            return True
    base = re.sub(r"[（(][^）)]*[）)]", "", w).strip()
    if base and base in content:
        return True
    # 「赵横的狗腿子」→ 分段检查「赵横」「狗腿子」；「叶家弟子」→ 前缀「叶家」
    for seg in re.split("的", base or w):
        seg = seg.strip()
        if len(seg) >= 2 and seg in content:
            return True
    if len(base) >= 4 and base[:2] in content:
        return True
    for group in _WITNESS_GROUP_SETS:
        if any(s in w for s in group) and any(s in content for s in group):
            return True
    return False


def _plain_content(ch: DabaiChapterOutline) -> str:
    return re.sub(r"<[^>]+>", "", ch.content or "").strip()


_BRIDGE_VERBS = (
    "走", "回", "赶", "踏入", "来到", "返回", "潜", "奔", "离开", "回到",
    "赶回", "步入", "潜入", "赶往", "一路", "折返", "摸黑", "穿行", "转入",
)


def _check_location_bridge(
    ch: DabaiChapterOutline,
    prev_ch: DabaiChapterOutline,
    content: str,
    prev_tail: str = "",
) -> dict | None:
    """规则 DLB-03：跨场景且开篇未紧接上章末句时，须有位移交代。"""
    opening = content[:450]
    if opening_continues_prev_tail(prev_tail, opening):
        return None
    if not needs_location_bridge(prev_ch, ch, prev_tail):
        return None
    prev_loc = (prev_ch.location or "").strip()
    curr_loc = (ch.location or "").strip()
    if any(v in opening for v in _BRIDGE_VERBS):
        return None
    return {
        "rule_id": "DLB-03",
        "message": (
            f"衔接断层：上章场景「{prev_loc}」→本章「{curr_loc}」，"
            f"开篇450字未见位移/转场交代（走/回/潜/踏入等）"
        ),
        # 动词表+固定窗口的字面匹配易误报（如「心念一动已立在」无动词）。
        # 证据注入 LLM prompt 由其按正文裁决；LLM 正常时本警告被丢弃（见 _merge_report）。
        "llm_overridable": True,
    }


def _check_realm_regression(
    ch: DabaiChapterOutline,
    project: DabaiProject,
    content: str,
) -> dict | None:
    """规则 DLB-04（阻断）：主角名附近以现在时出现低于本章档位的境界词。

    双重收窄防误报（DBC-02 误报停用是前车之鉴）：
    ① 只查主角名 ±24 字窗口内的低境界词（他人处于低境界是正常剧情）；
    ② 回忆/对比/突破自述语境豁免（复用主线 realm_regression_hit）。
    """
    from app.services.dabai.consistency_check import realm_regression_hit
    from app.services.dabai.lab_ledger import protagonist_name

    rank = ch.realm_rank or 0
    if not rank or not content:
        return None
    levels = (project.power_ladder or {}).get("levels") or []
    lower = [
        str(lv.get("name") or "").strip() for lv in levels
        if isinstance(lv, dict) and int(lv.get("rank") or 0) < rank
        and str(lv.get("name") or "").strip()
    ]
    protag = (protagonist_name(project) or "").strip()
    if not lower or not protag:
        return None
    # 截取主角名附近窗口拼接后做回忆语境判定
    windows: list[str] = []
    start = 0
    while True:
        idx = content.find(protag, start)
        if idx < 0:
            break
        windows.append(content[max(0, idx - 24): idx + len(protag) + 24])
        start = idx + len(protag)
    near = "\n".join(windows)
    for name in lower:
        if name in near and realm_regression_hit(near, name):
            return {
                "rule_id": "DLB-04",
                "message": (
                    f"境界倒退：主角附近以现在时出现低于本章档位（第{rank}档）"
                    f"的境界「{name}」"
                ),
            }
    return None


def _rule_report(
    ch: DabaiChapterOutline,
    db: Session | None = None,
    project: DabaiProject | None = None,
    ctx: LabDraftContext | None = None,
) -> dict:
    """规则层：零 LLM 成本的硬检查。DLB-04/07/08/09 为阻断，其余 warning。"""
    content = _plain_content(ch)
    warnings: list[dict] = []
    blockers: list[dict] = []

    if project is not None:
        regression = _check_realm_regression(ch, project, content)
        if regression:
            blockers.append(regression)
        from app.services.dabai.lab_ledger import protagonist_name

        protag = (protagonist_name(project) or "").strip()
        blockers.extend(run_critical_rule_checks(
            project, ch, content, protagonist_name=protag,
        ))

    expected = ch.expected_words or 0
    if expected and content:
        ratio = len(content) / expected
        if ratio < 0.75 or ratio > 1.12:
            warnings.append({
                "rule_id": "DLB-01",
                "message": f"字数偏离：实际 {len(content)} 字 / 目标 {expected} 字（允许 ±12%）",
            })

    if (ch.chapter_number or 0) == 1 and content and project is not None:
        qc_ctx = {"benchmark": project.benchmark or {}}
        if not skip_ch1_cliche_lint(qc_ctx):
            cliche = prose_opening_cliche_hit(content[:450], ctx=qc_ctx)
            if cliche:
                msg, _ = cliche
                warnings.append({
                    "rule_id": OPENING_CLICHE_RULE_ID,
                    "message": msg,
                    "llm_overridable": False,
                })

    witnesses = [str(w) for w in (ch.witnesses or []) if str(w).strip()]
    missing = [w for w in witnesses if not _witness_in_content(w, content)]
    if witnesses and missing:
        msg = f"章纲见证者未出现在正文：{'、'.join(missing[:5])}"
        warn: dict = {"rule_id": "DLB-02", "message": msg}
        # 黄金第2章常为金手指私密验证，见证者误报率高 → 交 LLM 按分档口径裁决
        if (ch.chapter_number or 0) == 2:
            warn["llm_overridable"] = True
            warn["message"] = msg + "（黄金第2章：若 payoff 为系统/认主私密反馈可忽略）"
        warnings.append(warn)

    if db is not None and project is not None and (ch.chapter_number or 0) > 1:
        prev = (
            db.query(DabaiChapterOutline)
            .filter(
                DabaiChapterOutline.project_id == project.id,
                DabaiChapterOutline.chapter_number == ch.chapter_number - 1,
            )
            .first()
        )
        if prev:
            prev_tail = (ctx.prev_tail if ctx else "") or (prev.content or "").strip()
            if prev_tail and len(prev_tail) > 1200:
                prev_tail = prev_tail[-1200:]
            bridge = _check_location_bridge(ch, prev, content, prev_tail=prev_tail)
            if bridge:
                warnings.append(bridge)

    if db is not None and project is not None and content:
        phrase_hits = check_chapter_phrase_violations(
            db, project.id, int(ch.chapter_number or 0), content,
        )
        if phrase_hits:
            warnings.append({
                "rule_id": "DBQ-07",
                "message": f"近章禁词复述：{'、'.join(phrase_hits[:4])}",
                "llm_overridable": True,
            })

    if blockers:
        status = "blocked"
        score = 40
    elif warnings:
        status = "warning"
        score = 100 - min(len(warnings) * 10, 30)
    else:
        status = "ok"
        score = 100
    return {
        "status": status,
        "overall_score": score,
        "blockers": blockers,
        "warnings": warnings,
    }


def _next_chapters_block(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    *,
    limit: int = 2,
) -> str:
    """后续章纲摘要，供质检给出 future_chapter_suggestions。"""
    rows = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project.id,
            DabaiChapterOutline.chapter_number > (ch.chapter_number or 0),
        )
        .order_by(DabaiChapterOutline.chapter_number.asc())
        .limit(limit)
        .all()
    )
    if not rows:
        return ""
    parts: list[str] = []
    for nx in rows:
        witnesses = "、".join(str(w) for w in (nx.witnesses or []) if str(w).strip())
        parts.append(
            f"第{nx.chapter_number}章《{nx.title or ''}》"
            f" 场景={nx.location or '—'} 爽点={nx.shuang_type or '—'}\n"
            f"  钩子={str(nx.end_hook or '')[:60]}"
            + (f" 见证者={witnesses}" if witnesses else "")
        )
    return "\n".join(parts)


async def run_lab_quality(
    svc,
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    *,
    with_llm: bool = True,
    source: str = "manual",
) -> dict:
    """lab 质检入口：规则报告必出，LLM 报告可降级（llm_status 标记）。

    Args:
        svc: AIService（with_llm=False 时可传 None）。
        with_llm: False 时只跑规则（快速校验）。
    Returns:
        合并后的报告 dict（已落库）。
    """
    from app.services.dabai.qc_merge import _merge_report
    from app.services.dabai.lab_qc_feedback import attach_rewrite_prompt

    ctx = build_lab_draft_context(db, project, ch)
    rule = _rule_report(ch, db=db, project=project, ctx=ctx)
    bridge_evidence = next(
        (str(w.get("message") or "") for w in (rule.get("warnings") or [])
         if w.get("rule_id") == "DLB-03"),
        "",
    )

    llm_data: dict | None = None
    llm_status = "skipped"
    if with_llm:
        llm_status = "ok"
        try:
            from app.services.bootstrap.parse import parse_json
            from app.services.bootstrap.retry import call_with_retry

            prev_ch = None
            if (ch.chapter_number or 0) > 1:
                prev_ch = (
                    db.query(DabaiChapterOutline)
                    .filter(
                        DabaiChapterOutline.project_id == project.id,
                        DabaiChapterOutline.chapter_number == ch.chapter_number - 1,
                    )
                    .first()
                )
            plain = _plain_content(ch)
            protected_cast = collect_future_cast_names(
                db, project.id, int(ch.chapter_number or 0),
            )
            phrase_guard_block = build_phrase_guard_block(
                db, project.id, int(ch.chapter_number or 0),
            )
            system, user = build_lab_qc_prompt(
                project, ch, ctx,
                prev_ch=prev_ch,
                bridge_evidence=bridge_evidence,
                next_chapters_block=_next_chapters_block(db, project, ch),
                plain_content=plain,
                protected_cast=protected_cast,
                phrase_guard_block=phrase_guard_block,
            )
            raw = await call_with_retry(
                svc, system, user, max_tokens=1800, task="dabai.quality",
            )
            llm_data = parse_json(raw)
            if not isinstance(llm_data, dict):
                llm_status = "parse_error"
                llm_data = None
        except Exception as exc:  # noqa: BLE001
            logger.warning("dabai-lab LLM 质检降级 chapter=%s: %s", ch.id, exc)
            llm_status = "error"

    report = _merge_report(rule, llm_data, llm_status)
    report = attach_rewrite_prompt(report)
    report["version"] = LAB_QC_VERSION
    report["continuity_snapshot"] = _build_continuity_snapshot(db, project, ch, ctx=ctx)
    row = persist_lab_quality(db, project, ch, report, source=source)
    report["report_id"] = str(row.id)
    return report


def _build_continuity_snapshot(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    ctx=None,
) -> dict:
    """质检时刻的衔接上下文快照（供后台回归对比）。

    ctx: 调用方已组装的 LabDraftContext，传入则复用避免重复查库。
    """
    if ctx is None:
        ctx = build_lab_draft_context(db, project, ch)
    content = _plain_content(ch)
    head = content[:450]
    prev_ch = None
    if (ch.chapter_number or 0) > 1:
        prev_ch = (
            db.query(DabaiChapterOutline)
            .filter(
                DabaiChapterOutline.project_id == project.id,
                DabaiChapterOutline.chapter_number == ch.chapter_number - 1,
            )
            .first()
        )
    prev_loc = (prev_ch.location or "").strip() if prev_ch else ""
    curr_loc = (ch.location or "").strip()
    continues = opening_continues_prev_tail(ctx.prev_tail, head)
    bridge_needed = bool(prev_ch and needs_location_bridge(prev_ch, ch, ctx.prev_tail))
    return {
        "prev_outline_location": prev_loc,
        "curr_outline_location": curr_loc,
        "prev_tail_preview": (ctx.prev_tail or "")[-200:],
        "content_head_preview": head[:200],
        "opening_continues_prev_tail": continues,
        "location_bridge_needed": bridge_needed,
        "content_word_count": len(content),
    }


def persist_lab_quality(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    report: dict,
    *,
    source: str = "manual",
) -> DabaiQualityReport:
    """追加一条质检报告（保留历史，供后台回归）。"""
    content = _plain_content(ch)
    row = DabaiQualityReport(
        project_id=project.id,
        chapter_id=ch.id,
        chapter_number=ch.chapter_number,
        version=str(report.get("version") or LAB_QC_VERSION),
        status=str(report.get("status") or "ok"),
        overall_score=int(report.get("overall_score") or 0),
        source=(source or "manual")[:30],
        content_word_count=len(content),
        content_head_preview=content[:200],
        report=report,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
