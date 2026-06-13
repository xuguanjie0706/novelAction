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
from app.services.dabai.lab_draft_context import build_lab_draft_context
from dabai.first_chapter_opening import witness_stems
from app.services.dabai.lab_pre_warn import _build_lab_beat_block
from app.services.dabai.lab_prompt_shared import (
    has_location_gap,
    needs_location_bridge,
    opening_continues_prev_tail,
)

# 注意：quality_check 经 draft_stream → AIService → routers.ai 存在循环 import 链，
# 必须函数内延迟导入（见 run_lab_quality / _build_lab_qc_prompt）。

logger = logging.getLogger(__name__)

LAB_QC_VERSION = "dabai-lab-qc-v2"

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
) -> dict:
    """规则层：零 LLM 成本的硬检查。DLB-04 境界倒退为唯一阻断，其余 warning。"""
    content = _plain_content(ch)
    warnings: list[dict] = []
    blockers: list[dict] = []

    if project is not None:
        regression = _check_realm_regression(ch, project, content)
        if regression:
            blockers.append(regression)

    expected = ch.expected_words or 0
    if expected and content:
        ratio = len(content) / expected
        if ratio < 0.75 or ratio > 1.12:
            warnings.append({
                "rule_id": "DLB-01",
                "message": f"字数偏离：实际 {len(content)} 字 / 目标 {expected} 字（允许 ±12%）",
            })

    witnesses = [str(w) for w in (ch.witnesses or []) if str(w).strip()]
    missing = [w for w in witnesses if not _witness_in_content(w, content)]
    if witnesses and missing:
        warnings.append({
            "rule_id": "DLB-02",
            "message": f"章纲见证者未出现在正文：{'、'.join(missing[:5])}",
        })

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
            prev_tail = (prev.content or "").strip()
            prev_tail = prev_tail[-800:] if len(prev_tail) > 800 else prev_tail
            bridge = _check_location_bridge(ch, prev, content, prev_tail=prev_tail)
            if bridge:
                warnings.append(bridge)

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


def _build_lab_qc_prompt(
    ch: DabaiChapterOutline,
    *,
    prev_tail: str,
    prev_ch: DabaiChapterOutline | None = None,
    bridge_evidence: str = "",
    next_chapters_block: str = "",
) -> tuple[str, str]:
    """构造 LLM 质检 (system, user)。正文取头 4500 + 中段抽样 + 尾 1200。

    bridge_evidence: 规则层 DLB-03 证据文案。注入后由 LLM 按正文裁决衔接断层，
                     规则层不再事后压分（裁决权单轨，见 _merge_report 丢弃 overridable）。
    """
    from app.services.dabai.quality_check import _QC_SYSTEM

    content = _plain_content(ch)
    head = content[:4500]
    tail = content[-1200:] if len(content) > 5700 else ""
    # 中段抽样：head+tail 之外仍有正文时补 800 字，重复铺陈多发于中段
    mid = ""
    if len(content) > 6500:
        c = len(content) // 2
        mid = content[c - 400: c + 400]

    parts = [f"《第{ch.chapter_number}章 {ch.title or ''}》质检。"]
    if prev_tail.strip():
        parts.append(f"【上章结尾（本章开头应承接）】\n{prev_tail.strip()[-600:]}")
    if prev_ch and prev_tail.strip():
        prev_loc = (prev_ch.location or "").strip()
        curr_loc = (ch.location or "").strip()
        head = content[:450]
        outline_gap = has_location_gap(prev_loc, curr_loc)
        continues = opening_continues_prev_tail(prev_tail, head)
        if outline_gap and (continues or not needs_location_bridge(prev_ch, ch, prev_tail)):
            parts.append(
                "【衔接判定说明】上章章纲场景载体可能滞后，或本章开篇紧接上章末句同一瞬间。"
                "衔接分必须以【上章结尾】与【本章开头】正文为准：若人物/场景/动作连续，"
                "即使章纲 location 不同或缺少位移动词，continuity_score 也应 ≥85，"
                "continuity_issue 留空；禁止要求从章纲 location 重新走一遍或否定已发生的承接。"
            )
    if bridge_evidence.strip():
        parts.append(
            "【规则层证据（仅供参考，最终以正文为准裁决）】\n"
            f"{bridge_evidence.strip()}\n"
            "请基于【上章结尾】与【本章开头】正文判断是否真有衔接断层："
            "若正文已交代位移过程、或开篇紧接上章末句同一瞬间，则不扣分；"
            "若确属无交代瞬移到新场景，continuity_score 应 ≤60 并写明 continuity_issue。"
        )
    parts.append(f"【章纲五拍要素】\n{_build_lab_beat_block(ch)}")
    if next_chapters_block.strip():
        parts.append(
            "【后续章纲预览（供 future_chapter_suggestions 参考；勿剧透未写内容）】\n"
            f"{next_chapters_block.strip()}"
        )
    parts.append(f"【本章正文（开头部分）】\n{head}")
    if mid:
        parts.append(f"【本章正文（中段抽样，重点查重复铺陈/口水循环）】\n{mid}")
    if tail:
        parts.append(f"【本章正文（结尾部分）】\n{tail}")
    parts.append(
        "逐项检查后只返回 JSON：\n"
        "{\n"
        '  "continuity_score": 0-100,  // 开头是否承接【上章结尾】末句与钩子；'
        '以正文末句场景为准（非章纲location）；单章内已位移时不因缺位移动词扣分\n'
        '  "continuity_issue": "一句话，无问题留空",\n'
        '  "beats": {"yaqu": "pass|partial|miss", "trigger": "...", "yinbao": "...", '
        '"payoff": "...", "hook": "..."},  // 五拍是否逐项落实（payoff 须有见证者反应）\n'
        '  "beat_issues": ["未落实拍的具体问题，每条≤30字"],\n'
        '  "hook_score": 0-100,  // 章末钩子强度：能否让读者点开下一章\n'
        '  "hook_issue": "一句话，无问题留空",\n'
        '  "repetition_issue": "明显的重复铺陈/口水循环，无则留空",\n'
        '  "chapter_suggestions": ["≤3条针对【本章正文】的可执行修改建议，禁止文采类"],\n'
        '  "future_chapter_suggestions": ["≤2条对后续章节写作/章纲执行的提醒'
        '（基于本章遗留问题与【后续章纲预览】，勿编造未给出的章纲）"],\n'
        '  "rewrite_prompt": "若本章综合质量不佳（衔接/五拍/钩子有明显短板），'
        '写一段150字内可直接交给写手的重写指令（先写必须保留什么，再写必须改什么）；'
        '质量尚可则留空",\n'
        '  "suggestions": ["与 chapter_suggestions 相同，兼容旧字段"]\n'
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
    source: str = "manual",
) -> dict:
    """lab 质检入口：规则报告必出，LLM 报告可降级（llm_status 标记）。

    Args:
        svc: AIService（with_llm=False 时可传 None）。
        with_llm: False 时只跑规则（快速校验）。
    Returns:
        合并后的报告 dict（已落库）。
    """
    from app.services.dabai.quality_check import _merge_report
    from app.services.dabai.lab_qc_feedback import attach_rewrite_prompt

    rule = _rule_report(ch, db=db, project=project)
    bridge_evidence = next(
        (str(w.get("message") or "") for w in (rule.get("warnings") or [])
         if w.get("rule_id") == "DLB-03"),
        "",
    )

    ctx = None
    llm_data: dict | None = None
    llm_status = "skipped"
    if with_llm:
        llm_status = "ok"
        try:
            from app.services.bootstrap.parse import parse_json
            from app.services.bootstrap.retry import call_with_retry

            ctx = build_lab_draft_context(db, project, ch)
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
            system, user = _build_lab_qc_prompt(
                ch, prev_tail=ctx.prev_tail, prev_ch=prev_ch,
                bridge_evidence=bridge_evidence,
                next_chapters_block=_next_chapters_block(db, project, ch),
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
