"""
gated_draft_routes.py — 质量门控写作端点

资源边界：
  - 本模块负责「起笔 → 自动质检 → 未达标则重写 → 循环」的全链路编排。
  - 单次起笔/续写（无循环）仍走 draft_routes.draft-assist/stream。
  - 质检逻辑复用 AIService.quality_check；存库逻辑内联（避免额外 HTTP 跳转）。

SSE 协议（JSON lines，prefix: ``data: ``）：
  gate_config   — 循环开始前推送生效配置
  attempt_start — 本轮起笔开始（strategy: initial | patch | full_rewrite）
  text          — 正文片段（与普通 draft-assist 格式完全一致）
  attempt_done  — 本轮起笔结束，附字数
  qc_running    — 质检开始
  qc_result     — 质检结果（passed / score / subscribe_intent / suggestions）
  gate_passed   — 达标，循环结束
  rewrite_queued— 未达标，即将进行下一轮（附策略）
  gate_failed   — 达到最大次数仍未达标，章节置 needs_review
  error         — 不可恢复错误
  [DONE]        — 流结束标记
"""
from __future__ import annotations

import json
import re
import textwrap
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Chapter,
    ChapterVersion,
    Character,
    MemoryChunk,
    OutlineNode,
    PowerSystem,
    Project,
    StoryLine,
    WorldSetting,
)
from app.routers.ai.context import (
    build_chapter_index_context,
    build_continuity_context,
    build_plot_dossier_context,
    format_world_setting_context,
)
from app.routers.ai.draft_routes import _build_draft_context
from app.routers.ai.quality_debt import sync_quality_debts
from app.routers.ai.schemas import GatedDraftRequest
from app.routers.ai.text_utils import plain_text
from app.services.ai_service import AIService
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block

router = APIRouter()

# ── 默认配置 ────────────────────────────────────────────────────
_DEFAULT_CONFIG: dict = {
    "auto_quality_gate": True,
    "min_overall_score": 6.0,       # 0-10；默认偏低，不干扰日常写作
    "min_subscribe_intent": 6.0,    # 章末追读意愿；专项门槛，独立于 overall
    "max_rewrite_attempts": 3,      # 最大尝试次数（含首次）
}


def _get_writing_config(project: Project, override: dict | None = None) -> dict:
    """
    合并项目级 writing_config 与请求级 override_config，返回最终生效配置。

    优先级：override_config > project.extra.writing_config > 内置默认值。

    @param project: 已加载的 Project ORM 对象
    @param override: 请求体中的临时覆盖字段（可为空）
    @returns 包含 auto_quality_gate / min_overall_score /
             min_subscribe_intent / max_rewrite_attempts 的配置 dict
    """
    cfg = dict(_DEFAULT_CONFIG)
    project_extra = getattr(project, "extra", None) or {}
    if isinstance(project_extra, dict):
        stored = project_extra.get("writing_config")
        if isinstance(stored, dict):
            cfg.update({k: v for k, v in stored.items() if k in _DEFAULT_CONFIG})
    if override and isinstance(override, dict):
        cfg.update({k: v for k, v in override.items() if k in _DEFAULT_CONFIG})
    # 值域保护
    cfg["min_overall_score"] = max(0.0, min(10.0, float(cfg["min_overall_score"])))
    cfg["min_subscribe_intent"] = max(0.0, min(10.0, float(cfg["min_subscribe_intent"])))
    cfg["max_rewrite_attempts"] = max(1, min(5, int(cfg["max_rewrite_attempts"])))
    return cfg


def _count_words_plain(text: str) -> int:
    """简易中文字数统计（去 HTML 标签）。"""
    clean = re.sub(r"<[^>]+>", "", text or "")
    chinese = len(re.findall(r"[一-鿿]", clean))
    english = len(re.findall(r"[a-zA-Z]+", clean))
    return chinese + english


def _plain_text_from_html(html: str) -> str:
    """HTML → 纯文本（去标签、保留换行语义）。"""
    text = re.sub(r"<br\s*/?>", "\n", html or "")
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _save_chapter_content(db: Session, chapter: Chapter, plain_draft: str, attempt: int) -> None:
    """
    将本轮生成的纯文本稿保存到 Chapter，并创建 ChapterVersion 快照。

    @param db: SQLAlchemy Session
    @param chapter: Chapter ORM 对象（将被就地修改）
    @param plain_draft: 本轮生成的纯文本正文（不含索引块）
    @param attempt: 当前尝试次数（写入快照 note）
    """
    # 纯文本 → HTML（每段一 <p>）
    blocks = plain_draft.split("\n\n")
    html_content = "\n".join(
        f"<p>{b.strip().replace(chr(10), '<br>')}</p>"
        for b in blocks if b.strip()
    ) or "<p></p>"

    word_count = _count_words_plain(plain_draft)

    # 先快照旧内容（首轮如果有旧内容）
    if chapter.content and chapter.content.strip():
        snap = ChapterVersion(
            chapter_id=chapter.id,
            content=chapter.content,
            word_count=_count_words_plain(_plain_text_from_html(chapter.content)),
            note=f"质量门控第{attempt}轮起笔前自动备份",
            is_auto=True,
        )
        db.add(snap)

    chapter.content = html_content
    chapter.manuscript_raw_snapshot = plain_draft
    chapter.word_count = word_count
    chapter.status = "writing"
    chapter.gated_draft_attempts = attempt
    db.commit()
    db.refresh(chapter)


async def _run_quality_check_inline(
    db: Session,
    chapter: Chapter,
    project: Project,
    project_id: str,
    large_context: bool,
    svc: AIService,
) -> dict:
    """
    在 gated 循环中内联执行质检，不走 HTTP 路由。

    复用 AIService.quality_check；上下文组装与 quality_routes 保持一致。

    @param db: SQLAlchemy Session
    @param chapter: 已保存最新内容的 Chapter 对象
    @param project: Project 对象
    @param project_id: 项目 UUID 字符串
    @param large_context: 是否大上下文模式（gemini）
    @param svc: 已初始化的 AIService 实例
    @returns quality_check 返回的 dict（含 overall_score / dimensions / suggestions / issues）
    @raises Exception: AI 调用失败时向上抛出
    """
    memory_query = (
        db.query(MemoryChunk)
        .outerjoin(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(MemoryChunk.project_id == project_id)
        .order_by(func.coalesce(Chapter.sort_order, MemoryChunk.chapter_number, 0).asc())
    )
    memories = memory_query.limit(200 if large_context else 50).all()

    settings = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id
    ).all()

    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()

    def _skill_names(known_skills) -> str:
        if not known_skills:
            return "无"
        names = [
            sk.get("skill_name", "") if isinstance(sk, dict) else str(sk)
            for sk in known_skills[:5]
        ]
        return "、".join(n for n in names if n) or "无"

    character_states = [
        f"{c.name}：境界={c.current_realm or '未知'}，"
        f"位置={c.current_location or '未知'}，"
        f"状态={c.current_status or 'alive'}，"
        f"已知技能=[{_skill_names(c.known_skills)}]"
        for c in characters
    ]

    active_storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["active", "climax"])
    ).all()
    storylines_context = [
        f"{s.name}（{s.line_type}，{s.status}）：{s.core_conflict or s.description or ''}"
        for s in active_storylines
    ]

    power_systems = db.query(PowerSystem).filter(
        PowerSystem.project_id == project_id
    ).all()
    power_systems_summary = []
    for ps in power_systems:
        if large_context:
            levels = []
            for level in (ps.levels or []):
                if isinstance(level, dict):
                    rank = level.get("rank")
                    name = level.get("name") or ""
                    req_str = level.get("requirement") or level.get("description") or ""
                    levels.append(f"{rank}.{name}({req_str})" if rank else f"{name}({req_str})")
                else:
                    levels.append(str(level))
            rules = ps.special_rules or ps.breakthrough_condition or ps.description or ""
            power_systems_summary.append(
                f"{ps.name}：等级={' > '.join(levels) or '未知'}；"
                f"主角当前={ps.protagonist_current_rank or '未知'}；规则={rules}"
            )
        else:
            highest_level = "未知"
            if ps.levels:
                last_level = ps.levels[-1]
                if isinstance(last_level, dict):
                    highest_level = last_level.get("name", "") or "未知"
                else:
                    highest_level = str(last_level) or "未知"
            power_systems_summary.append(
                f"{ps.name}：最高境界={highest_level}，主角当前={ps.protagonist_current_rank or '未知'}"
            )

    # 大纲上下文
    outline_context = ""
    node: OutlineNode | None = None
    if chapter.outline_node_id:
        node = db.query(OutlineNode).filter(OutlineNode.id == chapter.outline_node_id).first()
        if node:
            parts = []
            if node.summary:
                parts.append(f"本章摘要：{node.summary}")
            if large_context and node.hook:
                parts.append(f"开篇钩子：{node.hook}")
            if large_context and node.conflict:
                parts.append(f"核心冲突：{node.conflict}")
            if large_context and node.highlight:
                parts.append(f"章末方向：{node.highlight}")
            if node.power_milestone:
                parts.append(f"实力里程碑：{node.power_milestone}")
            if node.emotional_tone:
                parts.append(f"情感基调：{node.emotional_tone}")
            if node.foreshadows_laid:
                foreshadow_descs = [
                    f.get("description", "") if isinstance(f, dict) else str(f)
                    for f in node.foreshadows_laid[:3]
                ]
                parts.append(f"本章埋下伏笔：{'；'.join(foreshadow_descs)}")
            outline_context = "；".join(parts)

    continuity_ctx = build_continuity_context(
        db=db, project_id=project_id, chapter=chapter, outline_node=node,
    )
    chapter_index_ctx = build_chapter_index_context(
        db=db, project_id=project_id, chapter=chapter,
    )
    plot_dossier_ctx = build_plot_dossier_context(
        db=db, project_id=project_id, chapter=chapter, large_context=large_context,
    )

    check_types = [
        "plot", "character", "setting_consistency", "pacing",
        "hooks", "outline_alignment", "face_slap_payoff",
        "emotional_resonance", "subscribe_intent",
    ]

    result = await svc.quality_check(
        chapter_content=chapter.content,
        chapter_title=chapter.title,
        memories=[m.content for m in memories],
        settings_summary=[
            format_world_setting_context(s, content_limit=2400 if large_context else 260)
            for s in settings
        ],
        check_types=check_types,
        character_states=character_states,
        storylines_context=storylines_context,
        power_systems_summary=power_systems_summary,
        outline_context=outline_context,
        continuity_context=continuity_ctx,
        chapter_index_context=chapter_index_ctx,
        plot_dossier_context=plot_dossier_ctx,
    )

    # 写库（复用 quality_routes 逻辑）
    chapter.last_quality_score = result.get("overall_score")
    chapter.last_quality_report = result
    chapter.quality_checked_at = func.now()
    sync_quality_debts(db, project_id, chapter, result)
    db.commit()
    db.refresh(chapter)

    return result


def _check_passed(qc_result: dict, cfg: dict) -> tuple[bool, list[str]]:
    """
    判断质检是否通过门槛，返回 (passed, failing_dimension_names)。

    @param qc_result: quality_check 返回的完整结果 dict
    @param cfg: 生效的 writing_config dict
    @returns (True, []) 若通过；(False, [...]) 列出未达标维度名
    """
    overall = float(qc_result.get("overall_score") or 0)
    dims = qc_result.get("dimensions") or {}
    subscribe_intent = float((dims.get("subscribe_intent") or {}).get("score") or 0)

    failing: list[str] = []
    if overall < cfg["min_overall_score"]:
        failing.append(f"overall_score({overall:.1f}<{cfg['min_overall_score']})")
    if subscribe_intent < cfg["min_subscribe_intent"]:
        failing.append(f"subscribe_intent({subscribe_intent:.1f}<{cfg['min_subscribe_intent']})")

    return (len(failing) == 0), failing


def _build_rewrite_prompt(
    qc_result: dict,
    user_prompt: str,
    strategy: str,
    attempt: int,
) -> str:
    """
    根据质检结果与重写策略，构造注入起笔 user_prompt 的修复指令块。

    策略：
      - "patch"        ：定点修复失分区域，保留通过维度的内容结构
      - "full_rewrite" ：全量重写，所有建议作为硬约束，温度更高

    @param qc_result: 上轮质检结果
    @param user_prompt: 原始用户 prompt（透传，保留作者意图）
    @param strategy: "patch" | "full_rewrite"
    @param attempt: 当前尝试轮次（第几次重写）
    @returns 拼接后的完整 user_prompt 字符串
    """
    dims = qc_result.get("dimensions") or {}
    suggestions = qc_result.get("suggestions") or []
    issues = qc_result.get("issues") or []
    overall = qc_result.get("overall_score", 0)

    # 找出失分维度（< 7 视为需要改进）
    weak_dims = [
        f"{k}（{v.get('score', '?')}分）：{v.get('comment', '')}"
        for k, v in dims.items()
        if isinstance(v, dict) and float(v.get("score") or 10) < 7
    ]

    # 找出较好维度（≥ 8 分）
    strong_dims = [k for k, v in dims.items() if isinstance(v, dict) and float(v.get("score") or 0) >= 8]

    if strategy == "patch":
        block = textwrap.dedent(f"""

        ===【质量门控 · 第{attempt}轮 · 定点修复】===
        上轮整体得分：{overall}/10，未达门槛，需要修复以下失分区域。

        ▍需重点改善的维度：
        {chr(10).join(f"  • {d}" for d in weak_dims) if weak_dims else "  （无明显失分维度，请整体提升）"}

        ▍编辑具体建议（逐条落实）：
        {chr(10).join(f"  {i+1}. {s}" for i, s in enumerate(suggestions[:5]))}

        ▍已发现的一致性/钩子问题：
        {chr(10).join(f"  • {iss.get('description', '')}" for iss in issues[:3]) if issues else "  （无）"}

        ▍表现良好的维度（保持现有结构，不必推翻）：{', '.join(strong_dims) if strong_dims else '无'}

        写作要求：
        - 重写时只针对失分原因修改对应段落，其余段落可沿用上轮结构
        - 特别关注章末钩子（subscribe_intent）——最后一段必须制造悬念或爽感，让读者忍不住翻下一页
        - 不要口号式敷衍：「林默内心一凛」之类的情绪标签无法替代具体的场景动作
        ===
        """)
    else:  # full_rewrite
        block = textwrap.dedent(f"""

        ===【质量门控 · 第{attempt}轮 · 全量重写】===
        上轮得分：{overall}/10，两次定点修复均未达标。
        本轮请完整重写本章，以下为硬约束（每一条都必须体现在正文中）：

        ▍必须解决的问题：
        {chr(10).join(f"  • {iss.get('description', '')}" for iss in issues[:5]) if issues else "  （无）"}

        ▍全部编辑建议（本轮均须落实）：
        {chr(10).join(f"  {i+1}. {s}" for i, s in enumerate(suggestions))}

        ▍必须满足的硬性要求：
        - 章末最后一段：制造追读钩子（悬念/爽感/伏笔揭开），不可以角色思考或旁白收尾
        - 逻辑连续：人物位置、境界、持有技能须与上一章复盘记录完全吻合
        - 打脸兑现：若本章大纲要求打脸/爽点，必须以具体场景动作落地，不可用「众人哗然」带过
        ===
        """)

    base = (user_prompt or "").strip()
    return (base + block).strip()


# ═══════════════════════════════════════════════════════════════
# 端点：gated-draft-stream（质量门控写作）
# ═══════════════════════════════════════════════════════════════

@router.post("/gated-draft-stream")
async def gated_draft_stream(
    project_id: str,
    req: GatedDraftRequest,
    db: Session = Depends(get_db),
):
    """
    质量门控写作：写稿 → 自动质检 → 未达标则重写 → 循环至通过或暂停。

    流程：
    1. 读取 project.extra.writing_config 合并请求 override_config
    2. 循环（最多 max_rewrite_attempts 次）：
       a. 起笔（第1轮=initial，第2轮=patch，第3轮=full_rewrite）
       b. 保存章节正文 + 创建 ChapterVersion 快照
       c. 内联质检（复用 AIService.quality_check）
       d. 检查 overall_score ≥ min_overall_score 且 subscribe_intent ≥ min_subscribe_intent
       e. 通过 → gate_passed，结束
       f. 未通过 → 生成重写 prompt，继续下一轮
    3. 全部尝试用完仍未通过 → chapter.status = needs_review，emit gate_failed

    SSE 事件见模块 docstring。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cfg = _get_writing_config(project, req.override_config)
    large_context = req.model_profile == "gemini"

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def event_stream() -> AsyncGenerator[str, None]:
        # 推送生效配置
        yield _sse({
            "event": "gate_config",
            "min_overall_score": cfg["min_overall_score"],
            "min_subscribe_intent": cfg["min_subscribe_intent"],
            "max_rewrite_attempts": cfg["max_rewrite_attempts"],
            "auto_quality_gate": cfg["auto_quality_gate"],
        })

        user_prompt_str = (req.user_prompt or "").strip()
        last_qc: dict | None = None
        passed = False
        # 跨轮复用上下文：多轮间项目静态数据/上一章状态/承诺/伏笔/质检债务全部不变；
        # 而 gated 始终 replace_existing=True，draft_assist_stream 内部不读 existing_content。
        # 仅第 1 轮构建一次，后续轮直接复用，省 DB 查询 + 拼接开销。
        ctx: dict | None = None

        for attempt in range(1, cfg["max_rewrite_attempts"] + 1):
            # ── 决定本轮策略 ───────────────────────────────────────────
            if attempt == 1:
                strategy = "initial"
            elif attempt == cfg["max_rewrite_attempts"]:
                strategy = "full_rewrite"
            else:
                strategy = "patch"

            # ── 若是重写轮，先把上轮 QC 建议注入 prompt ───────────────
            current_user_prompt = user_prompt_str
            if attempt > 1 and last_qc is not None:
                current_user_prompt = _build_rewrite_prompt(
                    qc_result=last_qc,
                    user_prompt=user_prompt_str,
                    strategy=strategy,
                    attempt=attempt,
                )

            yield _sse({
                "event": "attempt_start",
                "attempt": attempt,
                "max_attempts": cfg["max_rewrite_attempts"],
                "strategy": strategy,
            })

            # ── 刷新章节实体（保存正文用，仍每轮做）；上下文仅第 1 轮构建 ──
            db.refresh(chapter)

            if ctx is None:
                try:
                    ctx = _build_draft_context(db, project_id, chapter, project, large_context)
                except Exception as e:
                    yield _sse({"error": f"上下文构建失败：{e}"})
                    return

            # ── 流式生成正文，同时累积到 accumulated ──────────────────
            accumulated = ""
            try:
                async for chunk in svc.draft_assist_stream(
                    **ctx,
                    user_prompt=current_user_prompt,
                    replace_existing=True,  # 门控写作始终整章重写
                    stream_log_context={
                        "project_id": str(project_id),
                        "chapter_id": str(req.chapter_id),
                        "gated_attempt": attempt,
                    },
                ):
                    accumulated += chunk
                    yield _sse({"text": chunk})
            except Exception as e:
                yield _sse({"error": f"起笔失败（第{attempt}轮）：{e}"})
                return

            # 提取叙事正文（去掉索引块）
            narr, _ = split_plain_manuscript_and_index_block(accumulated)
            draft_body = narr.strip() if narr.strip() else accumulated.strip()
            if not draft_body:
                yield _sse({"error": f"第{attempt}轮未收到正文内容"})
                return

            word_count = _count_words_plain(draft_body)
            yield _sse({"event": "attempt_done", "attempt": attempt, "words": word_count})

            # ── 保存到 DB + 创建 ChapterVersion ───────────────────────
            try:
                _save_chapter_content(db, chapter, draft_body, attempt)
                db.refresh(chapter)
            except Exception as e:
                yield _sse({"error": f"保存失败（第{attempt}轮）：{e}"})
                return

            # ── 内联质检 ──────────────────────────────────────────────
            yield _sse({"event": "qc_running", "attempt": attempt})
            try:
                qc = await _run_quality_check_inline(
                    db=db,
                    chapter=chapter,
                    project=project,
                    project_id=project_id,
                    large_context=large_context,
                    svc=svc,
                )
                last_qc = qc
            except Exception as e:
                yield _sse({"error": f"质检失败（第{attempt}轮）：{e}"})
                return

            overall_score = float(qc.get("overall_score") or 0)
            dims = qc.get("dimensions") or {}
            subscribe_intent_score = float(
                (dims.get("subscribe_intent") or {}).get("score") or 0
            )

            yield _sse({
                "event": "qc_result",
                "attempt": attempt,
                "overall_score": overall_score,
                "subscribe_intent": subscribe_intent_score,
                "passed": False,  # 先假设未通过，后面覆写
                "dimensions": {
                    k: {
                        "score": v.get("score"),
                        "status": v.get("status"),
                        "comment": v.get("comment", ""),
                    }
                    for k, v in dims.items()
                    if isinstance(v, dict)
                },
                "suggestions": (qc.get("suggestions") or [])[:5],
                "summary": qc.get("summary", ""),
            })

            # ── 判断是否通过 ───────────────────────────────────────────
            ok, failing = _check_passed(qc, cfg)
            if ok:
                passed = True
                # 覆写最后一个 qc_result 中的 passed=False → 补发 gate_passed
                yield _sse({
                    "event": "gate_passed",
                    "attempt": attempt,
                    "overall_score": overall_score,
                    "subscribe_intent": subscribe_intent_score,
                })
                # 更新章节状态为 done
                chapter.status = "done"
                db.commit()
                break

            # ── 未通过，若还有机会则推进下一轮 ───────────────────────
            if attempt < cfg["max_rewrite_attempts"]:
                next_strategy = "full_rewrite" if attempt + 1 == cfg["max_rewrite_attempts"] else "patch"
                yield _sse({
                    "event": "rewrite_queued",
                    "attempt": attempt,
                    "next_attempt": attempt + 1,
                    "strategy": next_strategy,
                    "failing_dimensions": failing,
                    "overall_score": overall_score,
                    "subscribe_intent": subscribe_intent_score,
                })

        # ── 全部尝试耗尽 ───────────────────────────────────────────────
        if not passed:
            final_score = float((last_qc or {}).get("overall_score") or 0)
            final_subscribe = float(
                ((last_qc or {}).get("dimensions") or {})
                .get("subscribe_intent", {})
                .get("score") or 0
            )
            chapter.status = "needs_review"
            db.commit()
            yield _sse({
                "event": "gate_failed",
                "max_attempts": cfg["max_rewrite_attempts"],
                "final_score": final_score,
                "final_subscribe_intent": final_subscribe,
                "min_overall_score": cfg["min_overall_score"],
                "min_subscribe_intent": cfg["min_subscribe_intent"],
                "message": (
                    f"经过 {cfg['max_rewrite_attempts']} 次尝试仍未达标"
                    f"（综合分 {final_score:.1f}/{cfg['min_overall_score']}，"
                    f"订阅意愿 {final_subscribe:.1f}/{cfg['min_subscribe_intent']}），"
                    "章节已暂停，请人工审阅后决定下一步。"
                ),
            })

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
