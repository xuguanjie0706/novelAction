"""dabai 实验书架质检 prompt 组装 — 富上下文 + 黄金三章分档验收口径。

第 2 章常见误报根因：① 仅 600 字上章尾导致 LLM 判衔接弱；② 用第 3 章「当众打脸」
标准扣第 2 章「金手指见效」；③ DLB-02 见证者规则不区分私密验证章。
"""
from __future__ import annotations

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.services.dabai.lab_draft_context import LabDraftContext
from app.services.dabai.lab_pre_warn import _build_lab_beat_block
from app.services.dabai.lab_prompt_shared import (
    has_location_gap,
    needs_location_bridge,
    opening_continues_prev_tail,
)
from dabai.golden_finger_bind import is_awakening_chapter, prose_bind_instructions
from dabai.non_system import prefers_non_system

# 与 quality_check._QC_SYSTEM 同文，避免 import 环（quality_check → draft_stream → routers）
_QC_SYSTEM_BASE = (
    "你是番茄/七猫大白文责编，负责结构化质检。注意：大白文取向——"
    "大白话、短句、口语化、解释直白都**不扣分**；"
    "禁止提出「增强文采」「多留白」「提升文学性」类建议。只返回 JSON。"
)

_LAB_QC_SYSTEM = (
    _QC_SYSTEM_BASE + "\n"
    "【黄金三章分档验收 · 勿混用标准】\n"
    "  第1章：主题定制憋屈 + 章末留金手指/危机钩子；不要求当众打脸。\n"
    "  第2章：金手指见效/绑定/首战试探；★不要求第3章级当众大打脸★；"
    "payoff 可为面板验证、私密小爽、能力初显；见证者缺席时若正文有系统/器物反馈可判 pass。\n"
    "  第3章：第一次当众打脸 + 见证者分级反应。\n"
    "衔接分必须以【上章正文实际结尾】与【本章开头】为准，非章纲 location。\n"
    "【叙事视角验收（限知第三人称）】正文须全程贴住主角："
    "出现上帝视角旁白（写主角不可能知道的他人内心/幕后真相/未来结果/设定来历全貌）、"
    "或作者下场分析点评（『其实这是…』『殊不知…』『这正是…的奥妙』），"
    "或新事物（道具/金手指/能力/陌生人）登场时主角不懵、无人解释也无自我疑问、"
    "却被旁白或主角直接报出名称来历用法数值——均属缺陷，"
    "须在 chapter_suggestions 写一条 [视角] 前缀的修复建议，并相应压低 hook_score/beats 评价。"
)

def golden_chapter_calibration(
    ch: DabaiChapterOutline,
    project: DabaiProject,
) -> str:
    """按章号注入验收口径，降低黄金第2章被误扣。"""
    num = int(ch.chapter_number or 0)
    if num == 1:
        return (
            "【本章验收口径 · 黄金第1章】重点查：开篇冲突是否贴题、憋屈是否具体、"
            "章末是否留下可追读钩子；勿要求金手指已完全绑定或已当众打脸。"
        )
    if num == 2:
        gf = project.golden_finger or {}
        gf_name = gf.get("name") or "金手指"
        return (
            "【本章验收口径 · 黄金第2章】任务=「金手指见效」，不是「第一次当众大打脸」（那是第3章）。"
            f"重点查：①紧接第1章末句/钩子；②{gf_name}首次提示/绑定/验证是否写清；"
            "③允许憋屈拍较短、payoff 为私密小爽（面板/识海/认主反馈）；"
            "④勿因缺少满场围观惊呼而判 payoff miss；"
            "⑤ beat.trigger 若体现疑→证→择即 pass/partial 均可，勿苛求当众爆发。"
        )
    if num == 3:
        return (
            "【本章验收口径 · 黄金第3章】重点查：第一次当众打脸 + 见证者分级反应；"
            "payoff 须有明确观众与量化爽感。"
        )
    return ""


def awakening_qc_note(ch: DabaiChapterOutline, project: DabaiProject) -> str:
    """金手指觉醒章补充验收说明。"""
    gf = project.golden_finger or {}
    artifact = prefers_non_system({
        "logline": project.logline or "",
        "positioning": project.positioning or {},
        "golden_finger": gf,
    })
    ch_dict = {
        "chapter_number": ch.chapter_number,
        "title": ch.title,
        "yinbao": getattr(ch, "yinbao", "") or "",
        "end_hook": getattr(ch, "end_hook", "") or "",
        "emotion_turn": getattr(ch, "emotion_turn", "") or "",
        "yaqu_setup": getattr(ch, "yaqu_setup", "") or "",
    }
    if not is_awakening_chapter(
        ch_dict, golden_finger_name=gf.get("name", ""), artifact=artifact,
    ):
        return ""
    bind = prose_bind_instructions(
        gf_name=gf.get("name", ""), artifact=artifact,
    ).strip()
    return (
        "【金手指绑定章 · 质检口径】本章属首次觉醒/绑定，"
        "trigger/yinbao 验收疑→证→择是否写清（可快但不可跳）；"
        "不要求第3章级当众打脸。\n" + bind
    )


def context_blocks_for_qc(ctx: LabDraftContext) -> str:
    """从写章同源上下文抽取质检注入块（时间轴/上章全文/末钩）。"""
    parts: list[str] = []
    if ctx.narrative_state_block.strip():
        block = ctx.narrative_state_block.strip()
        if len(block) > 6000:
            block = block[:5500] + "\n……（前情略）……"
        parts.append(block)
    if ctx.prev_full_block.strip():
        parts.append(ctx.prev_full_block.strip())
    elif ctx.prev_tail.strip():
        parts.append(
            "【上章结尾（本章开篇须紧接续写）】\n" + ctx.prev_tail.strip()[-1200:]
        )
    if ctx.prev_hook_block.strip():
        parts.append(ctx.prev_hook_block.strip())
    if ctx.recent_plot_block.strip() and not ctx.narrative_state_block.strip():
        parts.append(ctx.recent_plot_block.strip())
    return "\n\n".join(parts)


def build_lab_qc_prompt(
    project: DabaiProject,
    ch: DabaiChapterOutline,
    ctx: LabDraftContext,
    *,
    prev_ch: DabaiChapterOutline | None = None,
    bridge_evidence: str = "",
    next_chapters_block: str = "",
    plain_content: str = "",
) -> tuple[str, str]:
    """构造 LLM 质检 (system, user)。"""
    content = plain_content
    head = content[:4500]
    tail = content[-1200:] if len(content) > 5700 else ""
    mid = ""
    if len(content) > 6500:
        c = len(content) // 2
        mid = content[c - 400: c + 400]

    parts = [f"《第{ch.chapter_number}章 {ch.title or ''}》质检。"]
    cal = golden_chapter_calibration(ch, project)
    if cal:
        parts.append(cal)
    awaken = awakening_qc_note(ch, project)
    if awaken:
        parts.append(awaken)

    ctx_block = context_blocks_for_qc(ctx)
    if ctx_block:
        parts.append(ctx_block)

    if prev_ch and ctx.prev_tail.strip():
        prev_loc = (prev_ch.location or "").strip()
        curr_loc = (ch.location or "").strip()
        head_open = content[:450]
        outline_gap = has_location_gap(prev_loc, curr_loc)
        continues = opening_continues_prev_tail(ctx.prev_tail, head_open)
        if outline_gap and (continues or not needs_location_bridge(prev_ch, ch, ctx.prev_tail)):
            parts.append(
                "【衔接判定说明】上章章纲场景载体可能滞后，或本章开篇紧接上章末句同一瞬间。"
                "continuity_score 必须以【上章正文结尾】与【本章开头】为准："
                "若人物/场景/动作连续，即使章纲 location 不同或缺少位移动词，也应 ≥85，"
                "continuity_issue 留空；禁止要求从章纲 location 重走一遍。"
            )
    if bridge_evidence.strip():
        parts.append(
            "【规则层证据（仅供参考，最终以正文为准裁决）】\n"
            f"{bridge_evidence.strip()}\n"
            "若正文已交代位移或紧接上章末句同一瞬间，则不扣分。"
        )

    parts.append(f"【章纲五拍要素】\n{_build_lab_beat_block(ch)}")
    if next_chapters_block.strip():
        parts.append(
            "【后续章纲预览（供 future_chapter_suggestions 参考）】\n"
            f"{next_chapters_block.strip()}"
        )
    parts.append(f"【本章正文（开头部分）】\n{head}")
    if mid:
        parts.append(f"【本章正文（中段抽样）】\n{mid}")
    if tail:
        parts.append(f"【本章正文（结尾部分）】\n{tail}")

    num = int(ch.chapter_number or 0)
    payoff_note = ""
    if num == 2:
        payoff_note = (
            "payoff：黄金第2章允许「私密小爽/系统验证」，不必当众打脸；"
        )
    parts.append(
        "逐项检查后只返回 JSON：\n"
        "{\n"
        '  "continuity_score": 0-100,\n'
        '  "continuity_issue": "无问题留空",\n'
        '  "beats": {"yaqu": "pass|partial|miss", "trigger": "...", "yinbao": "...", '
        '"payoff": "...", "hook": "..."},\n'
        f"  // {payoff_note}payoff 须有见证者反应——黄金第2章可用系统/器物反馈替代围观\n"
        '  "beat_issues": [],\n'
        '  "hook_score": 0-100,\n'
        '  "hook_issue": "",\n'
        '  "repetition_issue": "",\n'
        '  "chapter_suggestions": ["≤3条，禁止文采类"],\n'
        '  "future_chapter_suggestions": ["≤2条"],\n'
        '  "rewrite_prompt": "质量尚可留空",\n'
        '  "suggestions": []\n'
        "}"
    )
    return _LAB_QC_SYSTEM, "\n\n".join(parts)
