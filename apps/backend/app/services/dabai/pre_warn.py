"""dabai 写前导演单（LLM 写作简报）— 写前裁决事实冲突 + 指导正文怎么写。

设计动机（2026-06）：dabai 单次生成把「事实调和」与「创作」挤在一个高温写作调用里：
章纲五拍是卷展开期批量生成的，写到第 N 章时实际剧情已与章纲漂移（境界/位置/人物关系），
写章模型要自己裁决图谱块/前情块/章纲谁说了算，裁决错了正文就错，质检 v2 写后才发现。
本模块在写前用一次低温调用产出「导演单」：

  - fact_lock        开笔事实锁定（境界/位置/在场/禁止出现）——冲突由 LLM 裁决，非规则硬断
  - conflict_notes   章纲与既有事实的冲突及弥合写法
  - opening_directive 开头第一段怎么承接上章实际结尾
  - beat_execution   五拍逐拍「在当前事实下怎么落」
  - bridge_directives 仅当确实存在位置/境界变化时给交代写法（LLM 确认，规避规则误报）
  - reminders        一句话提醒

为什么不是纯规则预警：DBC-02 地点正则因误报停用是前车之鉴——错误硬指令注入 prompt
比不注入更伤正文。为什么不搬通用线主编审稿：伏笔日程/转场菜单 dabai 线不维护，
writing_brief 的活五拍已经干了，整段大 prompt 增量信息少。

降级原则：LLM 失败/解析失败 → 返回空简报，写章走现状无简报路径，绝不阻塞。
持久化：结果落 PreWriteWarningRecord（result.version=dabai-prewarn-v1）；
整章重写时复用本章最新记录，避免重复耗时与简报漂移。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.models import Chapter, OutlineNode, PreWriteWarningRecord, Project
from app.services.dabai.draft_prompt import build_dabai_chapter_elements_block
from app.services.dabai.outline_plan import chapter_display_number

if TYPE_CHECKING:
    from app.services.dabai.draft_context import DabaiDraftContext

logger = logging.getLogger(__name__)

PREWARN_VERSION = "dabai-prewarn-v1"

_BEAT_KEYS = ("yaqu", "trigger", "yinbao", "payoff", "hook")
_BEAT_LABELS = {
    "yaqu": "①憋屈",
    "trigger": "②扳机",
    "yinbao": "③引爆",
    "payoff": "④爽点",
    "hook": "⑤钩子",
}

_PREWARN_SYSTEM = (
    "你是番茄/七猫大白文的责编兼导演，在作者落笔前出一份「导演单」。硬要求：\n"
    "1. 事实以【主角当前状态】【本章出场人物当前状态】【前情提要】【相关记忆】为准；\n"
    "1a. ★conflict_notes 只收录「真矛盾」——即：按章纲字面写就会与已写事实直接打架、"
    "读者一眼看出穿帮的硬伤。仅限这几类：已死/已离场的人物被要求出场；主角境界倒退或"
    "无依据跳级（与面板/记忆不符）；人物立场或状态明显相反（如前文已吓破胆/已臣服，"
    "章纲却让其逞凶/再敌对）；已消耗或已失去的资产被要求再用；地点或时间线硬冲突。\n"
    "1b. ★以下一律不算冲突，conflict_notes 留空 []，直接在 beat_execution 里按事实自然落笔即可："
    "章纲是粗线条而正文需补细节；情节顺势演进、措辞不同；程度或语气的轻微差异。"
    "宁可漏报，不要把正常细化写成「冲突裁决」；本章无硬伤就返回 []；\n"
    "2. 所有指令必须具体可执行（写什么、怎么切入），禁止「增强文采」「多留白」类建议；\n"
    "3. bridge_directives 只在确实存在位置/境界变化需要交代时给出，没有就留空数组，"
    "不要凭空编造移动；\n"
    "4. 每个字段一两句话，简短直接。只返回 JSON，不要任何额外文字。"
)


def build_prewarn_prompt(
    project: Project,
    chapter: Chapter,
    plan: OutlineNode | None,
    context: "DabaiDraftContext | None",
    prev_tail: str,
) -> tuple[str, str]:
    """构造导演单 (system, user)。上下文块复用写章已组装的四块，不重复查库。"""
    gf = (project.extra or {}).get("golden_finger") or {}
    ch_no = chapter_display_number(chapter)

    parts = [
        f"《{project.title}》第{ch_no}章 写前导演单。",
        f"金手指：{gf.get('name', '')}（{gf.get('core_ability', '')}）",
    ]
    for block in (
        (context.graph_block if context else ""),
        (context.recent_plot_block if context else ""),
        (context.memory_block if context else ""),
        (context.char_state_block if context else ""),
    ):
        if block and block.strip():
            parts.append(block.strip())
    if prev_tail.strip():
        parts.append(f"【上章结尾（正文开头须紧接续写）】\n{prev_tail.strip()[-600:]}")
    parts.append("【本章章纲五拍（卷展开期生成，可能与上述事实漂移）】")
    parts.append(build_dabai_chapter_elements_block(plan))
    parts.append(
        "对照以上资料完成裁决与指导，只返回 JSON：\n"
        "{\n"
        '  "fact_lock": {\n'
        '    "realm": "本章开笔时主角境界（以事实源为准，精确名称或档位）",\n'
        '    "location": "开笔位置",\n'
        '    "on_stage": ["确认可出场的人物"],\n'
        '    "forbidden": ["本章不能出现的能力/人物/道具（还没获得/已死/不在场）"]\n'
        "  },\n"
        '  "conflict_notes": ["章纲与事实的冲突及弥合写法，每条≤40字；无则空数组"],\n'
        '  "opening_directive": "开头第一段具体写法，必须正面承接上章结尾末句场景，1-2句",\n'
        '  "beat_execution": {"yaqu": "在当前事实下这拍怎么落，1句", "trigger": "...", '
        '"yinbao": "...", "payoff": "...（含见证者反应怎么递进）", "hook": "..."},\n'
        '  "bridge_directives": ["仅当确实需要交代位置/境界变化时：具体怎么交代；无则空数组"],\n'
        '  "reminders": ["≤3条一句话提醒"]\n'
        "}"
    )
    return _PREWARN_SYSTEM, "\n\n".join(parts)


def prewarn_cast_names(result: dict | None) -> list[str]:
    """导演单确认的本章出场人物名：优先 cast[].name，回退 fact_lock.on_stage。

    供写正文时按「本章实际出场人物」精确取人物档案——只取导演单点名的人，
    不再用章纲（可能漂移的）involved_characters/witnesses 全量。
    """
    if not isinstance(result, dict):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for c in (result.get("cast") or []):
        nm = str((c.get("name") if isinstance(c, dict) else c) or "").strip()
        if nm and nm not in seen:
            names.append(nm)
            seen.add(nm)
    if names:
        return names
    fact = result.get("fact_lock") or {}
    for raw in (fact.get("on_stage") or []):
        s = str(raw or "").strip()
        if s and s not in seen:
            names.append(s)
            seen.add(s)
    return names


def format_prewarn_block(result: dict | None) -> str:
    """导演单 JSON → 正文 prompt 注入块；结构不完整时返回空串（降级无简报）。"""
    if not isinstance(result, dict):
        return ""
    fact = result.get("fact_lock") or {}
    beats = result.get("beat_execution") or {}
    if not isinstance(fact, dict) or not isinstance(beats, dict):
        return ""

    lines = [
        "【写前导演单（五拍落法与 fact_lock.realm_end 须一致；"
        "开笔境界以【系统面板】/开笔基准为准，高于章纲节拍字面）】",
    ]
    fact_parts = []
    if fact.get("realm"):
        realm_seg = str(fact["realm"])
        sub = fact.get("realm_sub_rank")
        if sub not in (None, "") and "·第" not in realm_seg:
            try:
                realm_seg = f"{realm_seg}·第{int(sub)}层"
            except (TypeError, ValueError):
                pass
        fact_parts.append(f"开笔境界：{realm_seg}")
    if fact.get("realm_end") and fact.get("realm_end") != fact.get("realm"):
        end_seg = str(fact["realm_end"])
        end_sub = fact.get("realm_end_sub_rank")
        if end_sub not in (None, "") and "·第" not in end_seg:
            try:
                end_seg = f"{end_seg}·第{int(end_sub)}层"
            except (TypeError, ValueError):
                pass
        fact_parts.append(f"章末目标：{end_seg}")
    elif fact.get("realm_end"):
        fact_parts.append(f"章末境界：{fact['realm_end']}")
    if fact.get("location"):
        fact_parts.append(f"位置：{fact['location']}")
    on_stage = [str(x) for x in (fact.get("on_stage") or []) if x]
    if on_stage:
        fact_parts.append(f"在场：{'、'.join(on_stage[:8])}")
    if fact_parts:
        lines.append(f"- 开笔事实锁定：{'；'.join(fact_parts)}")
    cast = [c for c in (result.get("cast") or []) if isinstance(c, dict) and c.get("name")]
    if cast:
        segs = []
        for c in cast[:8]:
            nm = str(c.get("name")).strip()
            rs = str(c.get("reason") or "").strip()
            segs.append(f"{nm}（{rs}）" if rs else nm)
        lines.append("- 本章出场人物及出场原因（只写这些人，按原因落到对应拍）：" + "；".join(segs))
    forbidden = [str(x) for x in (fact.get("forbidden") or []) if x]
    if forbidden:
        lines.append(f"- 禁止出现：{'；'.join(forbidden[:5])}")
    for note in [str(x) for x in (result.get("conflict_notes") or []) if x][:4]:
        lines.append(f"- 冲突裁决：{note}")
    for note in [str(x) for x in (result.get("setup_alignment") or []) if x][:4]:
        lines.append(f"- 开局写法对齐：{note}")
    opening = str(result.get("opening_directive") or "").strip()
    if opening:
        lines.append(f"- 开头写法：{opening}")
    setup = str(result.get("setup_check") or "").strip()
    if setup and setup not in ("无", "无关键反转", "none", "None", "N/A", "/"):
        lines.append(f"- 铺垫依据（反转/获得须立得住）：{setup}")
    beat_parts = [
        f"{_BEAT_LABELS[k]}：{str(beats.get(k)).strip()}"
        for k in _BEAT_KEYS
        if str(beats.get(k) or "").strip()
    ]
    if beat_parts:
        lines.append("- 五拍执行：" + "；".join(beat_parts))
    for bridge in [str(x) for x in (result.get("bridge_directives") or []) if x][:3]:
        lines.append(f"- 衔接交代：{bridge}")
    for spec in [s for s in (result.get("asset_specs") or []) if isinstance(s, dict)][:6]:
        name = str(spec.get("name") or "").strip()
        segs = [
            f"{lbl}：{str(spec.get(key)).strip()}"
            for key, lbl in (("usage", "用法"), ("cost", "代价"),
                             ("progression", "进阶"), ("restriction", "限制"))
            if str(spec.get(key) or "").strip()
        ]
        if name and segs:
            lines.append(f"- 技能/道具规格〔{name}〕（须照此写，不得另编）：{'｜'.join(segs)}")
    for rem in [str(x) for x in (result.get("reminders") or []) if x][:3]:
        lines.append(f"- 提醒：{rem}")
    return "\n".join(lines) if len(lines) > 1 else ""


# ──────────────────────── 持久化与复用 ────────────────────────

def _find_reusable_record(
    db: Session, project_id: str, chapter_id: str
) -> PreWriteWarningRecord | None:
    """本章最新一条 dabai 导演单记录（version 匹配且非解析失败）。"""
    rec = (
        db.query(PreWriteWarningRecord)
        .filter(
            PreWriteWarningRecord.project_id == project_id,
            PreWriteWarningRecord.chapter_id == chapter_id,
        )
        .order_by(PreWriteWarningRecord.created_at.desc())
        .first()
    )
    if not rec:
        return None
    result = rec.result if isinstance(rec.result, dict) else {}
    if result.get("version") != PREWARN_VERSION or result.get("parse_failed"):
        return None
    return rec


def _persist_record(
    db: Session,
    project: Project,
    chapter: Chapter,
    plan_summary: str,
    result: dict,
    profile: str,
) -> PreWriteWarningRecord:
    rec = PreWriteWarningRecord(
        project_id=project.id,
        chapter_id=chapter.id,
        chapter_number=chapter.sort_order or 0,
        chapter_plan_summary=(plan_summary or "")[:500],
        model_profile=profile if profile in ("local", "gemini") else "local",
        llm_provider_id=None,
        result=result,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def _done_payload(result: dict, *, brief: str, record_id: str | None, reused: bool) -> dict:
    """pre_warn_done SSE 载荷（dabai 变体，前端按需消费）。"""
    return {
        "event": "pre_warn_done",
        "dabai_mode": True,
        "ok": True,
        "version": PREWARN_VERSION,
        "fact_lock": result.get("fact_lock") or {},
        "conflict_notes": (result.get("conflict_notes") or [])[:4],
        "opening_directive": str(result.get("opening_directive") or "")[:200],
        "beat_execution": result.get("beat_execution") or {},
        "bridge_directives": (result.get("bridge_directives") or [])[:3],
        "reminders": (result.get("reminders") or [])[:3],
        "brief_injected": bool(brief),
        "record_id": record_id,
        "reused": reused,
    }


# ──────────────────────── 编排入口 ────────────────────────

async def resolve_dabai_pre_warn(
    svc: Any,
    db: Session,
    project: Project,
    chapter: Chapter,
    plan: OutlineNode | None,
    context: "DabaiDraftContext | None",
    prev_tail: str,
    *,
    reuse_if_exists: bool = False,
) -> tuple[str, dict]:
    """生成（或复用）本章导演单。

    Args:
        reuse_if_exists: True（通常伴随整章重写）时若本章已有有效记录则跳过 LLM。

    Returns:
        (brief_block, pre_warn_done SSE 载荷)；任何失败 → ("", 含 error 的载荷)，不抛出。
    """
    if reuse_if_exists:
        rec = _find_reusable_record(db, str(project.id), str(chapter.id))
        if rec is not None:
            brief = format_prewarn_block(rec.result)
            if brief:
                return brief, _done_payload(
                    rec.result, brief=brief, record_id=str(rec.id), reused=True
                )

    try:
        from app.services.bootstrap.parse import parse_json
        from app.services.bootstrap.retry import call_with_retry

        system, user = build_prewarn_prompt(project, chapter, plan, context, prev_tail)
        raw = await call_with_retry(
            svc, system, user, max_tokens=1400, task="dabai.prewarn",
        )
        result = parse_json(raw)
        if not isinstance(result, dict):
            raise ValueError("导演单 JSON 解析失败")
        result["version"] = PREWARN_VERSION
        brief = format_prewarn_block(result)

        plan_summary = ""
        dabai = ((plan.extra or {}).get("dabai") if plan else {}) or {}
        if isinstance(dabai, dict):
            plan_summary = f"{dabai.get('shuang_type', '')} {dabai.get('shuang_payoff', '')}".strip()
        rec = _persist_record(
            db, project, chapter, plan_summary, result,
            getattr(svc, "profile", "local"),
        )
        return brief, _done_payload(result, brief=brief, record_id=str(rec.id), reused=False)
    except Exception as exc:
        logger.warning("dabai 导演单降级 chapter=%s: %s", chapter.id, exc)
        return "", {
            "event": "pre_warn_done",
            "dabai_mode": True,
            "ok": True,
            "version": PREWARN_VERSION,
            "brief_injected": False,
            "error": f"写前导演单失败（已降级继续写作）：{exc}",
        }
