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
    llm = rep.get("llm") if isinstance(rep.get("llm"), dict) else {}
    lines: list[str] = []
    for b in (rep.get("blockers") or [])[:2]:
        lines.append(f"  - [阻断]{str(b.get('message') or '')[:80]}")
    for s in (llm.get("suggestions") or [])[:3]:
        lines.append(f"  - {str(s)[:100]}")
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
