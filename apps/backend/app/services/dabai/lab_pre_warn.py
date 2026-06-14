"""dabai 实验书架写前导演单 — 裁决章纲 vs 上章事实冲突（dabai_* 表专用）。

复用主链路 ``format_prewarn_block`` 输出格式；结果落 ``dabai_pre_warn_records``
（PreWriteWarningRecord 表绑定精品文 Project，不可复用），每章保留最新一条。
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiPreWarnRecord
from app.services.dabai.lab_draft_context import LabDraftContext
from app.services.dabai.lab_prompt_shared import (
    build_power_ladder_block,
    build_witness_lock_block,
    sanitize_prewarn_result,
)
from app.services.dabai.pre_warn import _PREWARN_SYSTEM, format_prewarn_block

logger = logging.getLogger(__name__)

PREWARN_VERSION = "dabai-lab-prewarn-v2"

_OPENING_CHAPTER_RULE = (
    "【开篇章规则（尚无已写正文）】事实基准=【开局剧情资产】+【当前台账】+金手指设定，"
    "不是「已写正文」。章纲五拍若与开局资产/台账表述不一致："
    "直接在 opening_directive 与 beat_execution 按台账落法写；"
    "★conflict_notes 必须留空 []★——不要把正常的设定对齐写成「冲突裁决」。"
)

_LAB_PREWARN_SYSTEM = (
    _PREWARN_SYSTEM + "\n5. 开篇章（无已写正文）时 conflict_notes 必须 []，"
    "章纲与开局台账不一致只在 beat_execution 内按台账修正落法。"
)


def count_prior_written_chapters(
    db: Session, project_id: UUID, before_chapter: int,
) -> int:
    """当前章之前已有正文的章数（开篇章判定用）。"""
    if before_chapter <= 1:
        return 0
    return (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project_id,
            DabaiChapterOutline.chapter_number < before_chapter,
            DabaiChapterOutline.content.isnot(None),
            DabaiChapterOutline.content != "",
        )
        .count()
    )


def _opening_canon_block(project: DabaiProject) -> str:
    """开局剧情资产（debut=start）注入导演单，避免章纲与台账各说各话。"""
    from dabai.ctx_rich import assets_block

    ctx = {"story_assets": (project.extra or {}).get("story_assets") or {}}
    block = assets_block(ctx, volume_number=1)
    if not block.strip():
        return ""
    return block + (
        "\n★开篇章：上表 debut=start 的资产为既定开局设定；"
        "章纲若写错载体/获宝方式，按此块修正，不算与「已写正文」冲突。\n"
    )


def normalize_opening_prewarn(result: dict, *, opening_no_prior: bool) -> dict:
    """开篇章且无已写正文：LLM 误填的 conflict_notes 降级为 setup_alignment。"""
    if not opening_no_prior or not isinstance(result, dict):
        return result
    out = dict(result)
    notes = [str(x).strip() for x in (out.get("conflict_notes") or []) if str(x).strip()]
    if notes:
        out["setup_alignment"] = notes
        out["conflict_notes"] = []
    return out


class LabPreWarnError(RuntimeError):
    """导演单生成失败（strict 模式）。

    导演单是裁决「章纲 vs 已写事实漂移」的唯一防线；静默降级直写漂移章纲
    正是衔接断层最严重的来源，故 strict 模式下失败必须中止写章而非继续。
    """


def pre_warn_stale(result: dict | None, prev_content_hash: str) -> bool:
    """落库导演单是否已过期（上一章正文被重写过）。

    Args:
        result: 落库的导演单 result JSON（含 ``prev_content_hash``）。
        prev_content_hash: 当前上一章正文指纹（空串=无上章，不算过期）。
    """
    if not prev_content_hash:
        return False
    if not isinstance(result, dict) or not result:
        return True
    return str(result.get("prev_content_hash") or "") != prev_content_hash


def _build_lab_beat_block(ch: DabaiChapterOutline) -> str:
    witnesses = "、".join(ch.witnesses or []) if isinstance(ch.witnesses, list) else "围观众人"
    if not witnesses:
        witnesses = "围观众人"
    return "\n".join([
        f"  爽点类型：{ch.shuang_type or ''}",
        f"  ①憋屈：{ch.yaqu_setup or ''}",
        f"  ②转折扳机：{ch.emotion_turn or '（按章纲自行设计）'}",
        f"  ③引爆：{ch.yinbao or ''}",
        f"  ④爽点：{ch.shuang_payoff or ''}（见证者：{witnesses}）",
        f"  ⑤章末钩子：{ch.end_hook or ''}",
    ])


def build_lab_prewarn_prompt(
    project: DabaiProject,
    ch: DabaiChapterOutline,
    ctx: LabDraftContext,
    ledger_block: str = "",
    *,
    replace_existing: bool = False,
    bridge_evidence: str = "",
    opening_no_prior: bool = False,
    locked_spec_block: str = "",
) -> tuple[str, str]:
    """构造实验书架导演单 (system, user)。

    Args:
        ledger_block: 资产/关系台账（可空）。
        bridge_evidence: 规则层场景跨度证据（章纲 location gap 检测结果）。
            裁决权单轨：规则层只供证据，是否需要位移交代由导演单基于
            【上一章完整正文】实际结尾裁决（bridge_directives）。
    """
    gf = project.golden_finger or {}
    parts = [
        f"《{project.title or project.logline}》第{ch.chapter_number}章 写前导演单。",
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
        # 系统面板快照：导演单裁决冲突时需要知道精确的境界/技能冷却基准
        parts.append(ctx.panel_block.strip())
    if ctx.memory_block.strip():
        parts.append(ctx.memory_block.strip())
    if ctx.clue_block.strip():
        parts.append(ctx.clue_block.strip())
    canon = _opening_canon_block(project)
    if canon.strip():
        parts.append(canon.strip())
    if ledger_block.strip():
        parts.append(ledger_block.strip())
    if locked_spec_block.strip():
        parts.append(locked_spec_block.strip())
    if ctx.prev_full_block.strip():
        parts.append(ctx.prev_full_block.strip())
    elif ctx.prev_tail.strip():
        parts.append(f"【上章结尾（正文开头须紧接续写）】\n{ctx.prev_tail.strip()[-600:]}")
    if ctx.prev_hook_block.strip():
        parts.append(ctx.prev_hook_block.strip())
    if bridge_evidence.strip():
        parts.append(
            "【规则层场景跨度证据（仅供裁决参考，最终以上一章正文实际结尾为准）】\n"
            f"{bridge_evidence.strip()}\n"
            "请基于上一章正文实际结尾裁决：若开篇确需位移/转场交代，"
            "在 bridge_directives 给出具体写法；若上章末已在本章场景或停在"
            "「下一瞬间续写」边界，则 bridge_directives 留空并在 opening_directive "
            "中写明紧接续写的切入方式。"
        )
    parts.append("【本章章纲五拍（卷展开期生成，可能与上述事实漂移）】")
    parts.append(_build_lab_beat_block(ch))
    if opening_no_prior:
        parts.append(_OPENING_CHAPTER_RULE)
    if replace_existing:
        parts.append(
            "【重写要求】本章已有正文，beat_execution 须给出与常见模板不同的落法"
            "（换开笔切入/换扳机细节/换对话顺序），情节结果不变但写法须可区分。"
        )
    parts.append(
        "【可信度裁决（重要）】若本章含金手指获得/进阶或反败为胜/逆袭，必须在 setup_check "
        "写明「能赢/能获得的依据出自前文哪条事实或线索」——优先引用【既定事实记忆】"
        "/【未回收线索】/【系统面板】中已具备的境界·技能·法宝·伏笔；若前文确无铺垫，"
        "给一条当场立得住的依据（来历/代价/限制/破绽）并在 beat_execution.trigger·yinbao "
        "落实，禁止零铺垫硬翻、禁止临场冒出全新能力。本章无关键反转则填「无」。"
    )
    parts.append(
        "【技能/道具规格锁定（重要）】若本章有功法/法宝/金手指能力首次登场、首次施展或"
        "关键升级，必须在 asset_specs 为它写明详细规格：用法（怎么发动、效果是什么）、"
        "代价（消耗/反噬/冷却/副作用）、进阶（怎么变强、阶位路线）、限制（破绽/前置条件）。"
        "★已在【已锁定技能/道具规格】出现的，沿用其设定、可补未写的字段，禁止改写已有用法/代价。"
        "本章没有关键功法道具出场则 asset_specs 留空 []。分场与正文将照此规格写，不得另编。"
    )
    parts.append(
        "对照以上资料完成裁决与指导，只返回 JSON：\n"
        "{\n"
        '  "fact_lock": {\n'
        '    "realm": "本章开笔时主角境界（须用【本书境界体系】名称，禁止练气等外来体系）",\n'
        '    "location": "开笔位置",\n'
        '    "on_stage": ["确认可出场的人物（须用【人物称谓锁定】中的名字）"],\n'
        '    "forbidden": ["禁止出现的能力/情节（如金手指再绑定、写回废人）"]\n'
        "  },\n"
        '  "conflict_notes": ["只填「真矛盾」（按章纲写就会与已写事实硬碰、读者一眼穿帮：'
        '已死/已离场者出场、境界倒退或无依据跳级、立场状态明显相反如已吓破胆却逞凶、'
        '已消耗资产再用、地点时间线硬冲突），每条≤40字；粗线条补细节/顺势演进/措辞差异'
        '一律不算，留空[]；开篇章或无硬伤则[]"],\n'
        '  "opening_directive": "开头如何承接上章末句，1-2句",\n'
        '  "setup_check": "本章关键反转/获得的铺垫依据：引用前文哪条事实/线索/已具备能力，'
        '或当场立得住的依据；本章无关键反转填「无」",\n'
        '  "beat_execution": {"yaqu": "...", "trigger": "...", "yinbao": "...", '
        '"payoff": "...", "hook": "..."},\n'
        '  "bridge_directives": ["仅确实需要交代位置/境界变化时；无则[]"],\n'
        '  "asset_specs": [{"name": "功法/道具名", "kind": "skill|item|golden_finger", '
        '"usage": "用法（怎么用、效果）", "cost": "代价（消耗/反噬/冷却）", '
        '"progression": "进阶路线", "restriction": "限制/破绽"}],\n'
        '  "reminders": ["≤3条提醒"]\n'
        "}"
    )
    return _LAB_PREWARN_SYSTEM, "\n\n".join(parts)


def _done_payload(result: dict, *, brief: str) -> dict:
    return {
        "event": "pre_warn_done",
        "dabai_mode": True,
        "ok": True,
        "version": PREWARN_VERSION,
        "fact_lock": result.get("fact_lock") or {},
        "conflict_notes": (result.get("conflict_notes") or [])[:4],
        "setup_alignment": (result.get("setup_alignment") or [])[:4],
        "opening_directive": str(result.get("opening_directive") or "")[:200],
        "setup_check": str(result.get("setup_check") or "")[:200],
        "brief_injected": bool(brief),
    }


def load_lab_pre_warn(
    db: Session, chapter_id: UUID,
) -> tuple[str, dict | None]:
    """读取本章最新导演单，供按要素重写正文时复用（不重新 LLM 生成）。

    Returns:
        (brief_block, result_dict|None)；无落库记录时返回 ("", None)。
    """
    row = (
        db.query(DabaiPreWarnRecord)
        .filter(DabaiPreWarnRecord.chapter_id == chapter_id)
        .order_by(DabaiPreWarnRecord.created_at.desc())
        .first()
    )
    if not row or not isinstance(row.result, dict) or not row.result:
        return "", None
    brief = (row.brief or "").strip() or format_prewarn_block(row.result)
    return brief, row.result


def persist_lab_pre_warn(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    result: dict,
    brief: str,
) -> DabaiPreWarnRecord:
    """每章只保留最新一条导演单记录（先删后插，幂等）。"""
    db.query(DabaiPreWarnRecord).filter(
        DabaiPreWarnRecord.chapter_id == ch.id,
    ).delete(synchronize_session=False)
    row = DabaiPreWarnRecord(
        project_id=project.id, chapter_id=ch.id,
        chapter_number=ch.chapter_number,
        version=PREWARN_VERSION, result=result, brief=brief,
    )
    db.add(row)
    db.commit()
    return row


async def resolve_lab_pre_warn(
    svc: Any,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    ctx: LabDraftContext,
    db: Session | None = None,
    ledger_block: str = "",
    *,
    replace_existing: bool = False,
    bridge_evidence: str = "",
    strict: bool = False,
) -> tuple[str, dict, dict | None]:
    """生成导演单；传 db 时结果落库（持久化优先）。

    失败行为：
      - strict=True（lab 写章主路径）：抛 ``LabPreWarnError`` 中止写章——
        导演单缺席时直写漂移章纲产出的正是断层最严重的章，宁可让用户重试；
      - strict=False：降级为空简报继续（兼容旧调用方）。

    Returns:
        (brief_block, sse_done_payload, result_dict|None)
    """
    try:
        from app.services.bootstrap.parse import parse_json
        from app.services.bootstrap.retry import call_with_retry

        opening_no_prior = False
        if db is not None:
            opening_no_prior = count_prior_written_chapters(
                db, project.id, ch.chapter_number or 1,
            ) == 0 and int(ch.chapter_number or 1) == 1
        elif not (ctx.prev_full_block or ctx.prev_tail or "").strip():
            opening_no_prior = int(ch.chapter_number or 1) == 1

        locked_spec_block = ""
        if db is not None:
            from app.services.dabai.lab_asset_spec import build_locked_spec_block
            locked_spec_block = build_locked_spec_block(db, project, ch)
        system, user = build_lab_prewarn_prompt(
            project, ch, ctx, ledger_block,
            replace_existing=replace_existing, bridge_evidence=bridge_evidence,
            opening_no_prior=opening_no_prior, locked_spec_block=locked_spec_block,
        )
        prewarn_sampling = (
            {"temperature": 0.45, "presence_penalty": 0.15}
            if replace_existing else None
        )
        raw = await call_with_retry(
            svc, system, user, max_tokens=1400, task="dabai.prewarn",
            sampling=prewarn_sampling,
        )
        result = parse_json(raw)
        if not isinstance(result, dict):
            raise ValueError("导演单 JSON 解析失败")
        result = sanitize_prewarn_result(result, project)
        result = normalize_opening_prewarn(result, opening_no_prior=opening_no_prior)
        result["version"] = PREWARN_VERSION
        # 上章正文指纹：上一章重写后据此判定本导演单已过期，强制重生成
        result["prev_content_hash"] = ctx.prev_content_hash
        brief = format_prewarn_block(result)
        if not brief and strict:
            raise ValueError("导演单结构残缺（fact_lock/beat_execution 缺失）")
        if db is not None:
            try:
                from app.services.dabai.lab_asset_spec import apply_asset_specs
                spec_logs = apply_asset_specs(db, project, ch, result.get("asset_specs"))
                if spec_logs:
                    logger.info("dabai-lab 锁定技能/道具规格 chapter=%s: %s",
                                ch.chapter_number, "；".join(spec_logs))
                persist_lab_pre_warn(db, project, ch, result, brief)
            except Exception as persist_exc:  # noqa: BLE001
                logger.warning("dabai-lab 导演单落库失败 chapter=%s: %s", ch.id, persist_exc)
                db.rollback()
        return brief, _done_payload(result, brief=brief), result
    except Exception as exc:
        logger.warning("dabai-lab 导演单%s chapter=%s: %s",
                       "失败（strict 中止）" if strict else "降级", ch.id, exc)
        if strict:
            raise LabPreWarnError(
                f"写前导演单生成失败：{exc}。已中止本章写作（避免直写漂移章纲产生衔接断层），请重试。"
            ) from exc
        return "", {
            "event": "pre_warn_done",
            "dabai_mode": True,
            "ok": True,
            "version": PREWARN_VERSION,
            "brief_injected": False,
            "error": f"写前导演单失败（已降级继续写作）：{exc}",
        }, None
