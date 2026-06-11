"""dabai 实验书架写前导演单 — 裁决章纲 vs 上章事实冲突（dabai_* 表专用）。

复用主链路 ``format_prewarn_block`` 输出格式；结果落 ``dabai_pre_warn_records``
（PreWriteWarningRecord 表绑定精品文 Project，不可复用），每章保留最新一条。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiPreWarnRecord
from app.services.dabai.lab_draft_context import LabDraftContext
from app.services.dabai.pre_warn import _PREWARN_SYSTEM, format_prewarn_block

logger = logging.getLogger(__name__)

PREWARN_VERSION = "dabai-lab-prewarn-v1"


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
) -> tuple[str, str]:
    """构造实验书架导演单 (system, user)。ledger_block 为资产/关系台账（可空）。"""
    gf = project.golden_finger or {}
    parts = [
        f"《{project.title or project.logline}》第{ch.chapter_number}章 写前导演单。",
        f"金手指：{gf.get('name', '')}（{gf.get('core_ability', '')}）",
    ]
    if ctx.recent_plot_block.strip():
        parts.append(ctx.recent_plot_block.strip())
    if ctx.panel_block.strip():
        # 系统面板快照：导演单裁决冲突时需要知道精确的境界/技能冷却基准
        parts.append(ctx.panel_block.strip())
    if ctx.memory_block.strip():
        parts.append(ctx.memory_block.strip())
    if ctx.clue_block.strip():
        parts.append(ctx.clue_block.strip())
    if ledger_block.strip():
        parts.append(ledger_block.strip())
    if ctx.prev_tail.strip():
        parts.append(f"【上章结尾（正文开头须紧接续写）】\n{ctx.prev_tail.strip()[-600:]}")
    parts.append("【本章章纲五拍（卷展开期生成，可能与上述事实漂移）】")
    parts.append(_build_lab_beat_block(ch))
    if replace_existing:
        parts.append(
            "【重写要求】本章已有正文，beat_execution 须给出与常见模板不同的落法"
            "（换开笔切入/换扳机细节/换对话顺序），情节结果不变但写法须可区分。"
        )
    parts.append(
        "对照以上资料完成裁决与指导，只返回 JSON：\n"
        "{\n"
        '  "fact_lock": {\n'
        '    "realm": "本章开笔时主角境界",\n'
        '    "location": "开笔位置",\n'
        '    "on_stage": ["确认可出场的人物"],\n'
        '    "forbidden": ["禁止出现的能力/情节（如金手指再绑定、写回废人）"]\n'
        "  },\n"
        '  "conflict_notes": ["章纲与事实冲突及弥合写法，≤40字；无则[]"],\n'
        '  "opening_directive": "开头如何承接上章末句，1-2句",\n'
        '  "beat_execution": {"yaqu": "...", "trigger": "...", "yinbao": "...", '
        '"payoff": "...", "hook": "..."},\n'
        '  "bridge_directives": ["仅确实需要交代位置/境界变化时；无则[]"],\n'
        '  "reminders": ["≤3条提醒"]\n'
        "}"
    )
    return _PREWARN_SYSTEM, "\n\n".join(parts)


def _done_payload(result: dict, *, brief: str) -> dict:
    return {
        "event": "pre_warn_done",
        "dabai_mode": True,
        "ok": True,
        "version": PREWARN_VERSION,
        "fact_lock": result.get("fact_lock") or {},
        "conflict_notes": (result.get("conflict_notes") or [])[:4],
        "opening_directive": str(result.get("opening_directive") or "")[:200],
        "brief_injected": bool(brief),
    }


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
) -> tuple[str, dict]:
    """生成导演单；传 db 时结果落库（持久化优先）；失败降级为空简报，不阻塞写章。"""
    try:
        from app.services.bootstrap.parse import parse_json
        from app.services.bootstrap.retry import call_with_retry

        system, user = build_lab_prewarn_prompt(
            project, ch, ctx, ledger_block, replace_existing=replace_existing,
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
        result["version"] = PREWARN_VERSION
        brief = format_prewarn_block(result)
        if db is not None:
            try:
                persist_lab_pre_warn(db, project, ch, result, brief)
            except Exception as persist_exc:  # noqa: BLE001
                logger.warning("dabai-lab 导演单落库失败 chapter=%s: %s", ch.id, persist_exc)
                db.rollback()
        return brief, _done_payload(result, brief=brief)
    except Exception as exc:
        logger.warning("dabai-lab 导演单降级 chapter=%s: %s", ch.id, exc)
        return "", {
            "event": "pre_warn_done",
            "dabai_mode": True,
            "ok": True,
            "version": PREWARN_VERSION,
            "brief_injected": False,
            "error": f"写前导演单失败（已降级继续写作）：{exc}",
        }
