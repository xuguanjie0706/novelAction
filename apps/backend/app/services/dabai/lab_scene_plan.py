"""dabai 实验书架分场调度单 — 五拍章纲 → 2-4 场分场 → 正文按场推进。

设计动机（2026-06-12）：第一章质量差的结构性根因是「章纲五拍一句话直接糊
2000 字正文」，正常小说在章纲与正文之间有场面调度。本步在写前导演单之后、
正文之前插入一次低温 LLM 调用，把五拍拆成具体的「戏」：每场锁定地点/在场
人物/动作链/台词弹药/感官锚点/字数预算，正文模型照单拍戏而不是即兴编。

落 ``dabai_scene_plans``（每章保留最新一条）；失败降级为空块，不阻塞写章。
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiScenePlan
from app.services.dabai.lab_draft_context import LabDraftContext
from app.services.dabai.lab_prompt_shared import (
    build_power_ladder_block,
    build_witness_lock_block,
    build_location_bridge_block,
    has_location_gap,
    inject_prewarn_into_scene_plan,
)
from app.services.dabai.lab_word_budget import (
    chapter_word_target,
    finalize_scene_plan_result,
    scene_plan_from_row,
)

logger = logging.getLogger(__name__)

SCENEPLAN_VERSION = "dabai-lab-sceneplan-v2"


class LabScenePlanError(RuntimeError):
    """分场调度生成失败（strict 模式）：中止写章而非降级五拍直写。"""

_SCENEPLAN_SYSTEM = (
    "你是写了三十年白话爽文的老作者，现在做章前分场（场面调度），"
    "把一章的五拍节拍拆成 2-4 场可以直接照着写的『戏』。\n"
    "分场原则：\n"
    "1. 每场一个地点一个核心事件，场与场之间有明确的递进/转折，不许两场写同一件事；\n"
    "2. 五拍映射参考：场1=憋屈现场（压迫者带具体羞辱动作与台词）→ "
    "场2=扳机+引爆（金手指/反击的具体过程）→ 场3=爽点兑现（见证者分级反应）"
    "→ 可选场4=钩子收尾；可按本章实际合并或调整；\n"
    "2.5 黄金第一章特别要求：opening_line 必须让前3行就站在冲突现场"
    "（开打/开骂/开抢/濒死），禁止从天气、环境、回忆、世界观介绍开篇；\n"
    "2.6 非第1章：opening_line 必须落实【导演单】opening_directive；"
    "若 bridge_directives 非空，scenes[0] 必须是位移/承接场（写回途/进门/转场），"
    "冲突场从 scenes[1] 开始；禁止跳过位移直接写冲突。\n"
    "3. dialogue_ammo 是本场的台词弹药——大白文靠对话撑场面，"
    "每场给 2-3 句有锋芒的关键台词原话（羞辱原话/反击金句/围观惊呼），"
    "口语化、带人物身份感，禁止文绉绉；\n"
    "4. sensory_anchor 给一个具体可感的细节锚点（断剑上的缺口/掌心的汗/"
    "丹炉的焦味），正文用它落地，一场一个就够；\n"
    "5. 尊重给定的事实基准（前情/面板/台账/导演单），禁止编造未持有的能力；\n"
    "6. word_budget：各场预算之和必须 **严格等于** 章纲目标字数（见 user 首行），"
    "爽点/引爆场占大头，位移承接场可偏短；禁止自行放大总预算。\n"
    "只返回 JSON，不要任何解释。"
)


def _beat_lines(ch: DabaiChapterOutline) -> str:
    witnesses = "、".join(ch.witnesses or []) if isinstance(ch.witnesses, list) else ""
    return "\n".join([
        f"  爽点类型：{ch.shuang_type or ''}",
        f"  场景载体：{ch.location or '（未给，自行选一个具体地点+事件）'}",
        f"  ①憋屈：{ch.yaqu_setup or ''}",
        f"  ②转折扳机：{ch.emotion_turn or ''}",
        f"  ③引爆：{ch.yinbao or ''}",
        f"  ④爽点：{ch.shuang_payoff or ''}（见证者：{witnesses or '围观众人'}）",
        f"  ⑤章末钩子：{ch.end_hook or ''}",
    ])


def build_sceneplan_prompt(
    project: DabaiProject,
    ch: DabaiChapterOutline,
    ctx: LabDraftContext,
    pre_warn_block: str = "",
    ledger_block: str = "",
    pre_warn_result: dict | None = None,
    prev_ch: DabaiChapterOutline | None = None,
) -> tuple[str, str]:
    """构造分场调度 (system, user)。复用写章同一份上下文，不重复查库。"""
    gf = project.golden_finger or {}
    target = chapter_word_target(ch)
    per_scene = max(target // 3, 400)
    parts = [
        f"《{project.title or project.logline}》第{ch.chapter_number}章 分场调度。"
        f"★章纲目标字数 {target}（各场 word_budget 合计必须等于 {target}，不得超出）★。",
        f"金手指：{gf.get('name', '')}（{gf.get('core_ability', '')}）",
    ]
    ladder_block = build_power_ladder_block(project)
    if ladder_block:
        parts.append(ladder_block)
    witness_block = build_witness_lock_block(ch)
    if witness_block:
        parts.append(witness_block)
    if ctx.narrative_state_block.strip():
        parts.append(ctx.narrative_state_block.strip())
    if ctx.recent_plot_block.strip():
        parts.append(ctx.recent_plot_block.strip())
    if ctx.panel_block.strip():
        parts.append(ctx.panel_block.strip())
    if ctx.memory_block.strip():
        parts.append(ctx.memory_block.strip())
    if ledger_block.strip():
        parts.append(ledger_block.strip())
    if ctx.prev_tail.strip():
        parts.append(f"【上章结尾（场1须紧接续写）】\n{ctx.prev_tail.strip()[-800:]}")
    if ctx.prev_hook_block.strip():
        parts.append(ctx.prev_hook_block.strip())
    if pre_warn_block.strip():
        parts.append(pre_warn_block.strip())
    if pre_warn_result:
        opening_dir = str(pre_warn_result.get("opening_directive") or "").strip()
        bridges = pre_warn_result.get("bridge_directives") or []
        if opening_dir:
            parts.append(f"【导演单开篇指令（opening_line 必须体现）】\n{opening_dir}")
        if bridges:
            parts.append(
                "【导演单位移交代（须单独成 scenes[0] 承接场）】\n"
                + "\n".join(f"  - {b}" for b in bridges[:3])
            )
    if prev_ch:
        bridge_block = build_location_bridge_block(prev_ch, ch)
        if bridge_block:
            parts.append(bridge_block)
    parts.append("【本章章纲五拍】")
    parts.append(_beat_lines(ch))
    parts.append(
        "按上面资料分场，只返回 JSON：\n"
        "{\n"
        '  "opening_line": "开篇写法指令（≤50字，勿写完整首句正文）：从什么动作/对白/感官切入、'
        '前3行进冲突现场，禁止环境/回忆开篇",\n'
        '  "scenes": [\n'
        "    {\n"
        '      "order": 1, "name": "场名(≤8字)", "location": "具体地点",\n'
        '      "characters_on_stage": ["在场人物"],\n'
        '      "goal": "本场承担的节拍（憋屈/扳机/引爆/爽点/钩子）",\n'
        '      "event": "发生什么：具体动作链（谁做了什么→对方怎么接→局面怎么变）",\n'
        '      "dialogue_ammo": ["关键台词原话2-3句"],\n'
        '      "sensory_anchor": "1个具体感官细节",\n'
        '      "end_turn": "本场结尾的转折/递进（勾下一场）",\n'
        f'      "word_budget": {per_scene}\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"scenes 共 2-4 场，word_budget 合计必须等于 {target}（示例单场约 {per_scene}，按节拍自行分配）。"
    )
    return _SCENEPLAN_SYSTEM, "\n\n".join(parts)


def format_scene_block(result: dict) -> str:
    """分场 JSON → 注入正文 prompt 的调度块。结构残缺时返回空串（降级）。"""
    scenes = result.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return ""
    total = int(result.get("word_budget_total") or 0)
    if total <= 0:
        total = sum(int(s.get("word_budget") or 0) for s in scenes if isinstance(s, dict))
    lines = [
        "【分场调度（正文必须按场推进，禁止合并/跳场/自创新场；篇幅以各场 word_budget 为硬上限）】",
    ]
    if total > 0:
        lines.append(f"  全章预算合计 {total} 字（已与章纲 expected_words 对齐）")
    opening = str(result.get("opening_line") or "").strip()
    if opening:
        lines.append(f"  开篇指令（按指令自行开写，禁止照抄本行字句当正文首句）：{opening}")
    for i, sc in enumerate(scenes[:5], 1):
        if not isinstance(sc, dict):
            continue
        cast = "、".join(str(c) for c in (sc.get("characters_on_stage") or [])[:6])
        ammo = " / ".join(str(a) for a in (sc.get("dialogue_ammo") or [])[:3])
        lines.append(
            f"  ▸场{i}〔{sc.get('name', '')}｜{sc.get('location', '')}｜"
            f"约{sc.get('word_budget', '?')}字〕在场：{cast}"
        )
        if sc.get("event"):
            lines.append(f"    事件：{sc['event']}")
        if ammo:
            lines.append(f"    台词弹药（须用上，可微调措辞）：{ammo}")
        if sc.get("sensory_anchor"):
            lines.append(f"    感官锚点：{sc['sensory_anchor']}")
        if sc.get("end_turn"):
            lines.append(f"    场末转折：{sc['end_turn']}")
    lines.append(
        "  ★每场写细但控字：动作拆成连续画面、对话有来回，"
        "见证者反应按 愣住→不信→震惊→心服 走台阶；不得超过各场 word_budget 上限。"
    )
    return "\n".join(lines)


def _result_from_row(row: DabaiScenePlan, ch: DabaiChapterOutline) -> dict | None:
    return scene_plan_from_row(row.opening_line, row.scenes, ch)


def load_lab_scene_plan(db: Session, chapter_id: UUID) -> str:
    """读取本章最新分场注入块，供按要素重写正文时复用（不重新 LLM 生成）。"""
    row = (
        db.query(DabaiScenePlan)
        .filter(DabaiScenePlan.chapter_id == chapter_id)
        .order_by(DabaiScenePlan.created_at.desc())
        .first()
    )
    if not row:
        return ""
    brief = (row.brief or "").strip()
    if brief:
        return brief
    if row.scenes:
        return format_scene_block({
            "scenes": row.scenes,
            "opening_line": row.opening_line or "",
        })
    return ""


def load_lab_scene_plan_with_result(
    db: Session,
    ch: DabaiChapterOutline,
) -> tuple[str, dict | None]:
    """读取本章最新分场块 + 归一化后的 result dict。"""
    row = (
        db.query(DabaiScenePlan)
        .filter(DabaiScenePlan.chapter_id == ch.id)
        .order_by(DabaiScenePlan.created_at.desc())
        .first()
    )
    if not row:
        return "", None
    brief = (row.brief or "").strip()
    result = _result_from_row(row, ch)
    if result:
        brief = format_scene_block(result) or brief
    elif row.scenes:
        brief = format_scene_block({
            "opening_line": row.opening_line or "",
            "scenes": row.scenes,
        })
    return brief, result


def refresh_lab_scene_block(
    db: Session,
    ch: DabaiChapterOutline,
    *,
    prev_ch: DabaiChapterOutline | None,
    prev_tail: str,
    pre_warn_result: dict | None,
) -> tuple[str, dict | None]:
    """重写正文时按最新上章结尾重算分场块（剔除过时的位移承接场）。"""
    row = (
        db.query(DabaiScenePlan)
        .filter(DabaiScenePlan.chapter_id == ch.id)
        .order_by(DabaiScenePlan.created_at.desc())
        .first()
    )
    if not row or not row.scenes:
        return load_lab_scene_plan_with_result(db, ch)
    refreshed = inject_prewarn_into_scene_plan(
        {"opening_line": row.opening_line or "", "scenes": row.scenes},
        pre_warn_result,
        ch,
        prev_ch,
        prev_tail=prev_tail,
    )
    refreshed = finalize_scene_plan_result(refreshed, ch)
    brief = format_scene_block(refreshed)
    if brief:
        return brief, refreshed
    return load_lab_scene_plan_with_result(db, ch)


def persist_scene_plan(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    result: dict,
    brief: str,
) -> DabaiScenePlan:
    """每章只保留最新一条分场记录（先删后插，幂等）。"""
    db.query(DabaiScenePlan).filter(
        DabaiScenePlan.chapter_id == ch.id,
    ).delete(synchronize_session=False)
    row = DabaiScenePlan(
        project_id=project.id, chapter_id=ch.id,
        chapter_number=ch.chapter_number,
        version=SCENEPLAN_VERSION,
        scenes=result.get("scenes") or [],
        opening_line=str(result.get("opening_line") or ""),
        brief=brief,
    )
    db.add(row)
    db.commit()
    return row


async def resolve_lab_scene_plan(
    svc: Any,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    ctx: LabDraftContext,
    db: Session | None = None,
    pre_warn_block: str = "",
    ledger_block: str = "",
    pre_warn_result: dict | None = None,
    prev_ch: DabaiChapterOutline | None = None,
    *,
    replace_existing: bool = False,
    strict: bool = False,
) -> tuple[str, dict, dict | None]:
    """生成分场调度单；传 db 时落库（持久化优先）。

    失败行为：strict=True 抛 ``LabScenePlanError`` 中止写章（正文质量优先，
    五拍直写是断层与同质化的温床）；strict=False 降级空块继续（兼容旧调用方）。

    Returns:
        (scene_block 注入块, SSE scene_plan_done 事件 payload, 归一化后的 result dict)。
    """
    try:
        from app.services.bootstrap.parse import parse_json
        from app.services.bootstrap.retry import call_with_retry

        system, user = build_sceneplan_prompt(
            project, ch, ctx, pre_warn_block, ledger_block, pre_warn_result, prev_ch,
        )
        sampling = (
            {"temperature": 0.7, "presence_penalty": 0.2}
            if replace_existing else None
        )
        raw = await call_with_retry(
            svc, system, user, max_tokens=2000, task="dabai.sceneplan",
            sampling=sampling,
        )
        result = parse_json(raw)
        if not isinstance(result, dict):
            raise ValueError("分场 JSON 解析失败")
        result = inject_prewarn_into_scene_plan(
            result, pre_warn_result, ch, prev_ch, prev_tail=ctx.prev_tail,
        )
        result = finalize_scene_plan_result(result, ch)
        brief = format_scene_block(result)
        if not brief:
            raise ValueError("分场结构残缺（scenes 为空）")
        result["version"] = SCENEPLAN_VERSION
        if db is not None:
            try:
                persist_scene_plan(db, project, ch, result, brief)
            except Exception as persist_exc:  # noqa: BLE001
                logger.warning("dabai-lab 分场落库失败 chapter=%s: %s", ch.id, persist_exc)
                db.rollback()
        scenes = result.get("scenes") or []
        return brief, {
            "event": "scene_plan_done",
            "dabai_mode": True,
            "ok": True,
            "version": SCENEPLAN_VERSION,
            "scene_count": len(scenes),
            "scene_names": [str(s.get("name", "")) for s in scenes if isinstance(s, dict)][:5],
            "word_budget_total": result.get("word_budget_total"),
        }, result
    except Exception as exc:  # noqa: BLE001
        logger.warning("dabai-lab 分场%s chapter=%s: %s",
                       "失败（strict 中止）" if strict else "降级", ch.id, exc)
        if strict:
            raise LabScenePlanError(
                f"分场调度生成失败：{exc}。已中止本章写作（避免五拍直写产生断层），请重试。"
            ) from exc
        return "", {
            "event": "scene_plan_done",
            "dabai_mode": True,
            "ok": True,
            "version": SCENEPLAN_VERSION,
            "scene_count": 0,
            "error": f"分场调度失败（已降级为五拍直写）：{exc}",
        }, None
