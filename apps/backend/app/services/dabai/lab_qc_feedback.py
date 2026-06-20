"""dabai 实验书架质检「读端」— 报告回灌上游 prompt（修「只写不读」缺口）。

质检报告此前只落库展示；本模块把报告变成上游约束，两级回灌：
  - 章级 ``build_chapter_qc_feedback_block``：重写时注入上一版报告的
    suggestions / 未落实拍 / warning，重写优先修复而非只「换写法」；
  - 书级 ``build_project_qc_issue_block``：聚合各章最新报告的高频 rule_id，
    生成卷展开章纲 prompt 的「历史高频问题」块（对齐精品线
    OutlineIssueLog → feedback_block 的支柱一思想）。
"""
from __future__ import annotations

from collections import Counter
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline
from app.models.dabai_lab import DabaiQualityReport

# rule_id → 写给生成模型的规避指导语（不是给人看的报错文案）
_RULE_GUIDANCE: dict[str, str] = {
    "DLB-01": "正文字数贴住 expected_words（±12%），不注水不腰斩",
    "DLB-02": "章纲 witnesses 必须真实出场并给出分级反应（愣住→不信→震惊→心服）",
    "DLB-03": "跨场景章开篇先写位移/转场过程（怎么离开、经什么路径、怎么抵达），禁止无交代瞬移",
    "DLB-04": "境界不可倒退；提及旧境界须有「当年/突破自」类回忆语境",
    "DLB-05": "不得写死或永久移除后续章 involved 出场人物；本章须在 end_hook 处收笔",
    "DLB-06": "开篇须按 benchmark 改编换皮；禁止系统默认模板套话，禁止照搬对标书原句",
    "DBC-01": "境界不可倒退；提及旧境界须有回忆语境",
    "DBQ-01": "开篇必须正面承接上章结尾末句与钩子，禁止剧情重置",
    "DBQ-02": "五拍逐拍落实，payoff 必须写见证者的具体反应",
    "DBQ-03": "章末钩子要具体（更强敌人/更大机缘/打脸预告），禁用套话",
    "DBQ-04": "同一桥段只写一次，删掉重复铺陈/口水循环",
}


def _latest_reports_per_chapter(
    db: Session, project_id: UUID, limit: int = 200,
) -> list[DabaiQualityReport]:
    """每章只取最新一条报告（报告表为追加写，需按章去重）。"""
    rows = (
        db.query(DabaiQualityReport)
        .filter(DabaiQualityReport.project_id == project_id)
        .order_by(DabaiQualityReport.created_at.desc())
        .limit(limit)
        .all()
    )
    latest: dict[str, DabaiQualityReport] = {}
    for r in rows:
        key = str(r.chapter_id)
        if key not in latest:
            latest[key] = r
    return list(latest.values())


def build_chapter_qc_feedback_block(
    db: Session, ch: DabaiChapterOutline,
) -> str:
    """重写注入块：本章最新质检报告的可执行问题清单。无报告/无问题返回空串。"""
    row = (
        db.query(DabaiQualityReport)
        .filter(DabaiQualityReport.chapter_id == ch.id)
        .order_by(DabaiQualityReport.created_at.desc())
        .first()
    )
    if not row or not isinstance(row.report, dict):
        return ""
    rep = row.report
    score = int(rep.get("overall_score") or 0)
    rewrite_prompt = str(rep.get("rewrite_prompt") or "").strip()
    if score < 80 and rewrite_prompt:
        return (
            f"【上一版质检反馈（{score}分；重写必须逐条修复，"
            f"优先级高于「换写法」要求）】\n{rewrite_prompt[:1200]}"
        )
    llm = rep.get("llm") if isinstance(rep.get("llm"), dict) else {}
    lines: list[str] = []
    for b in (rep.get("blockers") or [])[:2]:
        lines.append(f"  - [阻断]{str(b.get('message') or '')[:80]}")
    chapter_tips = llm.get("chapter_suggestions") or llm.get("suggestions") or []
    for s in chapter_tips[:3]:
        lines.append(f"  - [本章]{str(s)[:100]}")
    for s in (llm.get("future_chapter_suggestions") or [])[:2]:
        lines.append(f"  - [后续]{str(s)[:100]}")
    for issue in (llm.get("beat_issues") or [])[:3]:
        lines.append(f"  - 五拍问题：{str(issue)[:60]}")
    for w in (rep.get("warnings") or [])[:3]:
        lines.append(f"  - {str(w.get('message') or '')[:80]}")
    if not lines:
        return ""
    return (
        f"【上一版质检反馈（{row.overall_score}分；重写必须逐条修复，"
        "优先级高于「换写法」要求）】\n" + "\n".join(dict.fromkeys(lines))
    )


REWRITE_SCORE_THRESHOLD = 80


def build_lab_rewrite_prompt(report: dict) -> str:
    """规则合成重写提示词（LLM 未给出 rewrite_prompt 时的兜底）。"""
    llm = report.get("llm") if isinstance(report.get("llm"), dict) else {}
    score = int(report.get("overall_score") or 0)
    lines = [f"【质检 {score} 分 · 重写本章正文，逐项修复下列问题】"]
    for b in (report.get("blockers") or [])[:2]:
        lines.append(f"- [阻断] {str(b.get('message') or '')[:100]}")
    if llm.get("continuity_issue") and int(llm.get("continuity_score") or 100) < 80:
        lines.append(f"- [衔接] {str(llm['continuity_issue'])[:100]}")
    for issue in (llm.get("beat_issues") or [])[:3]:
        lines.append(f"- [五拍] {str(issue)[:80]}")
    if llm.get("hook_issue") and int(llm.get("hook_score") or 100) < 80:
        lines.append(f"- [钩子] {str(llm['hook_issue'])[:100]}")
    for s in (llm.get("chapter_suggestions") or llm.get("suggestions") or [])[:3]:
        lines.append(f"- [本章] {str(s)[:100]}")
    for s in (llm.get("future_chapter_suggestions") or [])[:2]:
        lines.append(f"- [后续章注意] {str(s)[:100]}")
    for w in (report.get("warnings") or [])[:4]:
        lines.append(f"- [{w.get('rule_id')}] {str(w.get('message') or '')[:80]}")
    lines.append("- 保留已通过的五拍与衔接，只改失分部分；禁止文采堆砌。")
    return "\n".join(lines)[:1500]


def attach_rewrite_prompt(report: dict, *, threshold: int = REWRITE_SCORE_THRESHOLD) -> dict:
    """score<threshold 时落库顶层 rewrite_prompt（优先 LLM 产出，否则规则合成）。"""
    score = int(report.get("overall_score") or 0)
    llm = report.get("llm") if isinstance(report.get("llm"), dict) else {}
    llm_rp = str((llm or {}).get("rewrite_prompt") or "").strip()
    if score >= threshold:
        report["rewrite_prompt"] = ""
        return report
    report["rewrite_prompt"] = (llm_rp or build_lab_rewrite_prompt(report))[:1500]
    return report


def build_chapter_range_qc_block(
    db: Session,
    project_id: UUID,
    *,
    chapter_from: int,
    chapter_to: int,
) -> str:
    """按目标章号过滤质检报告中的 future_chapter_suggestions / 邻章建议。"""
    lines: list[str] = []
    for row in _latest_reports_per_chapter(db, project_id):
        rep = row.report if isinstance(row.report, dict) else {}
        ch_num = (
            db.query(DabaiChapterOutline.chapter_number)
            .filter(DabaiChapterOutline.id == row.chapter_id)
            .scalar()
        )
        if ch_num is None:
            continue
        src = int(ch_num)
        if src >= chapter_from:
            continue
        llm = rep.get("llm") if isinstance(rep.get("llm"), dict) else {}
        for s in (llm.get("future_chapter_suggestions") or [])[:3]:
            text = str(s).strip()
            if text:
                lines.append(f"  - [第{src}章质检→后续] {text[:120]}")
        score = int(rep.get("overall_score") or 0)
        if score < 70:
            for w in (rep.get("warnings") or [])[:2]:
                rid = str(w.get("rule_id") or "")
                if rid in _RULE_GUIDANCE:
                    lines.append(
                        f"  - [第{src}章×{rid}] {_RULE_GUIDANCE[rid][:80]}"
                    )
    if not lines:
        return ""
    deduped = list(dict.fromkeys(lines))[:12]
    return (
        f"【已写章节对第{chapter_from}～{chapter_to}章章纲的规避建议】\n"
        + "\n".join(deduped)
    )


def build_forward_qc_block(
    db: Session,
    project_id: UUID,
    *,
    target_chapter: int,
    lookback: int = 2,
) -> str:
    """前序章节质检的「后续章节建议」→ 注入目标章正文 prompt（首写也注入）。

    修「前瞻建议只进章纲/重写」的缺口：QC 给第 N 章的 future_chapter_suggestions
    此前仅在卷展开或本章重写时可见；写第 N 章正文（首稿）时拿不到。
    取目标章前 ``lookback`` 章（最贴近本章）最新报告的 future_chapter_suggestions
    注入，让前瞻建议真正落到正文。

    Args:
        target_chapter: 即将写作的章号 N。
        lookback: 回看前几章（默认 2：第 N-1、N-2 章的前瞻建议最相关）。
    """
    if target_chapter <= 1:
        return ""
    lines: list[str] = []
    for row in _latest_reports_per_chapter(db, project_id):
        rep = row.report if isinstance(row.report, dict) else {}
        ch_num = (
            db.query(DabaiChapterOutline.chapter_number)
            .filter(DabaiChapterOutline.id == row.chapter_id)
            .scalar()
        )
        if ch_num is None:
            continue
        src = int(ch_num)
        if not (target_chapter - lookback <= src < target_chapter):
            continue
        llm = rep.get("llm") if isinstance(rep.get("llm"), dict) else {}
        for s in (llm.get("future_chapter_suggestions") or [])[:3]:
            text = str(s).strip()
            if text:
                lines.append(f"  - [第{src}章质检前瞻] {text[:140]}")
    if not lines:
        return ""
    deduped = list(dict.fromkeys(lines))[:5]
    return (
        "【前序质检给本章的建议（须在正文落实，不是背景设定）】\n"
        + "\n".join(deduped)
        + "\n  执行要求：把上述建议当成本章要兑现的情节目标，"
        "顺着五拍自然写进剧情/动作/台词里——仍须守铺垫（关键转机先给依据）、"
        "限知视角（不剧透主角不可能知道的、不让他人凭空知情）与本书叙事烈度档；"
        "不要把建议原文当旁白说明贴出来。"
    )


def build_project_qc_issue_block(
    db: Session, project_id: UUID, *, top_n: int = 3, min_count: int = 2,
) -> str:
    """卷展开注入块：全书各章最新报告的高频 rule_id → 规避指导语。

    出现 < min_count 次的不注入（避免单次偶发问题污染全卷章纲）。
    """
    counts: Counter[str] = Counter()
    for row in _latest_reports_per_chapter(db, project_id):
        rep = row.report if isinstance(row.report, dict) else {}
        for w in (rep.get("warnings") or []) + (rep.get("blockers") or []):
            rid = str(w.get("rule_id") or "").strip()
            if rid:
                counts[rid] += 1
    top = [
        (rid, n) for rid, n in counts.most_common(top_n)
        if n >= min_count and rid in _RULE_GUIDANCE
    ]
    if not top:
        return ""
    lines = [f"  - {rid}×{n}：{_RULE_GUIDANCE[rid]}" for rid, n in top]
    return (
        "【历史高频质检问题（已写章节反复踩坑，本卷章纲必须从源头规避）】\n"
        + "\n".join(lines)
    )
