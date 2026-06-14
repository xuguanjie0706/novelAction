"""dabai 实验书架 — 按本章质检建议做外科手术式修订（轻上下文）。

与「按要素重写」不同：不注入预警/分场/记忆/台账，仅本章正文 + 质检报告。
适用场景：分数尚可、只需按 suggestions 定点修补，避免全链路重写引入新漂移。
"""
from __future__ import annotations

from typing import AsyncIterator

from app.models.dabai import DabaiChapterOutline
from app.services.dabai.lab_word_budget import chapter_word_target

_BEAT_LABELS = {
    "yaqu_setup": "憋屈",
    "emotion_turn": "转折",
    "yinbao": "引爆",
    "shuang_payoff": "爽点",
    "end_hook": "钩子",
}

_SYSTEM = (
    "你是网文精修编辑，专做【外科手术式修订】——根据质检报告修补已有正文，"
    "不是另起炉灶整章重写。\n"
    "硬要求：\n"
    "1. 只改质检指出的失分处；已通过的五拍/维度对应段落尽量原样保留；\n"
    "2. 情节结果、人物关系、境界与已写事实不变；禁止引入新角色/新道具/新能力；\n"
    "3. 大白话、短句、对话多；禁止堆环境描写与文采堆砌；\n"
    "4. 章末须落在原钩子方向（可加强不可弱化）；\n"
    "5. 只输出修订后完整正文，不要标题、对照表或修订说明。"
)


def _chapter_only_fixlist(rep: dict) -> str:
    """仅本章可执行修复项（不含后续章建议）。"""
    llm = rep.get("llm") if isinstance(rep.get("llm"), dict) else {}
    lines: list[str] = []
    rewrite_prompt = str(rep.get("rewrite_prompt") or "").strip()
    if rewrite_prompt:
        lines.append(rewrite_prompt)
    for b in (rep.get("blockers") or [])[:3]:
        lines.append(f"[阻断·{b.get('rule_id', '')}] {str(b.get('message') or '')[:120]}")
    chapter_tips = llm.get("chapter_suggestions") or llm.get("suggestions") or []
    for s in chapter_tips[:6]:
        text = str(s).strip()
        if text:
            lines.append(f"· {text[:160]}")
    if llm.get("continuity_issue") and int(llm.get("continuity_score") or 100) < 80:
        lines.append(f"[衔接] {str(llm['continuity_issue'])[:120]}")
    if llm.get("hook_issue") and int(llm.get("hook_score") or 100) < 80:
        lines.append(f"[钩子] {str(llm['hook_issue'])[:120]}")
    for issue in (llm.get("beat_issues") or [])[:4]:
        lines.append(f"[五拍] {str(issue)[:100]}")
    for w in (rep.get("warnings") or [])[:5]:
        lines.append(f"[{w.get('rule_id', '')}] {str(w.get('message') or '')[:100]}")
    if not lines:
        return ""
    deduped = list(dict.fromkeys(lines))
    return "\n".join(deduped)[:1800]


def _pass_summary(rep: dict) -> str:
    """已通过项摘要，提示模型勿动。"""
    llm = rep.get("llm") if isinstance(rep.get("llm"), dict) else {}
    parts: list[str] = []
    for key, label in _BEAT_LABELS.items():
        st = str((llm.get("beats") or {}).get(key) or "").lower()
        if st == "pass":
            parts.append(label)
    for dim, label in (
        ("continuity_score", "衔接"),
        ("beat_score", "五拍整体"),
        ("hook_score", "钩子"),
    ):
        if int(llm.get(dim) or 0) >= 80:
            parts.append(label)
    if not parts:
        return "（无明确 pass 项时，仍只改 fixlist 指出的段落，其余尽量保留）"
    return "、".join(parts)


def build_qc_patch_prompt(
    ch: DabaiChapterOutline,
    *,
    prior_content: str,
    report: dict,
    title: str = "",
) -> tuple[str, str]:
    """构造「本章正文 + 本章质检建议」修订 prompt。"""
    content = (prior_content or "").strip()
    fixlist = _chapter_only_fixlist(report)
    if not content or not fixlist:
        return "", ""

    llm = report.get("llm") if isinstance(report.get("llm"), dict) else {}
    score = int(report.get("overall_score") or 0)
    target = chapter_word_target(ch)
    lo = max(1600, target - int(target * 0.12))
    hi = target + int(target * 0.12)
    cur_len = len(content)

    beat_line = " | ".join(
        f"{_BEAT_LABELS[k]}·{(llm.get('beats') or {}).get(k, '?')}"
        for k in _BEAT_LABELS
    )
    score_line = (
        f"综合 {score} 分"
        f" | 衔接 {llm.get('continuity_score', '—')}"
        f" | 五拍 {llm.get('beat_score', '—')}"
        f" | 钩子 {llm.get('hook_score', '—')}"
    )

    user_parts = [
        f"《{title or '本书'}》第{ch.chapter_number}章「{ch.title or ''}」",
        f"目标 {target} 字（允许 {lo}～{hi}；当前约 {cur_len} 字，修订后尽量贴近目标）",
        f"【质检摘要】\n{score_line}\n{beat_line}",
        f"【已通过须保留（勿大改）】\n{_pass_summary(report)}",
        f"【本章必须修复（按优先级；不含后续章建议）】\n{fixlist}",
    ]
    if (ch.end_hook or "").strip():
        user_parts.append(f"【章末钩子（须保留方向）】\n{ch.end_hook.strip()}")
    user_parts.append(f"【待修订正文】\n{content[:15000]}")
    user_parts.append(
        "请输出修订后的完整正文。只改 fixlist 指出的失分处，其余段落尽量保留原表述。"
    )
    return _SYSTEM, "\n\n".join(user_parts)


def report_actionable_for_patch(report: dict | None) -> bool:
    if not report or not isinstance(report, dict):
        return False
    return bool(_chapter_only_fixlist(report).strip())


class QcPatchError(Exception):
    """按质检建议修订的前置校验失败。"""


def load_latest_qc_report_dict(db, chapter_id) -> dict | None:
    from app.models.dabai_lab import DabaiQualityReport

    row = (
        db.query(DabaiQualityReport)
        .filter(DabaiQualityReport.chapter_id == chapter_id)
        .order_by(DabaiQualityReport.created_at.desc())
        .first()
    )
    if not row or not isinstance(row.report, dict):
        return None
    return row.report


async def iter_qc_patch_chunks(
    db,
    ai,
    project,
    ch: DabaiChapterOutline,
    *,
    prior_content: str,
    user_instruction: str = "",
) -> AsyncIterator[str]:
    """校验并流式产出质检修订正文。"""
    if not (prior_content or "").strip():
        raise QcPatchError("本章尚无正文，无法按建议修订")
    rep = load_latest_qc_report_dict(db, ch.id)
    if not rep:
        raise QcPatchError("请先跑质检，暂无报告")
    if not report_actionable_for_patch(rep):
        raise QcPatchError("质检报告暂无可执行的本章修复建议")
    async for delta in stream_qc_patch_prose(
        ai,
        ch,
        prior_content=prior_content,
        report=rep,
        title=getattr(project, "title", "") or "",
        user_instruction=user_instruction,
    ):
        yield delta


async def stream_qc_patch_prose(
    ai,
    ch: DabaiChapterOutline,
    *,
    prior_content: str,
    report: dict,
    title: str = "",
    user_instruction: str = "",
) -> AsyncIterator[str]:
    """流式输出质检修订正文 delta。"""
    system, user_prompt = build_qc_patch_prompt(
        ch, prior_content=prior_content, report=report, title=title,
    )
    if not system or not user_prompt:
        raise ValueError("缺少正文或质检修复项，无法按建议修订")

    instr = (user_instruction or "").strip()
    if instr:
        system += "\n6. 【作者补充指令】在 fixlist 之上追加约束，仍须遵守上述硬要求。"
        user_prompt += f"\n\n【作者补充指令】\n{instr[:2000]}"

    hi = chapter_word_target(ch) + 200
    from app.services.dabai.draft_stream import dabai_draft_max_tokens

    async for delta in ai._stream_ai(
        system,
        user_prompt,
        task="dabai.qc_patch",
        max_tokens=dabai_draft_max_tokens(hi),
        sampling={"temperature": 0.55, "presence_penalty": 0.1, "frequency_penalty": 0.1},
    ):
        if delta:
            yield delta
