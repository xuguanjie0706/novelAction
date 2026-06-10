"""
gated_draft_routes.py — 质量门控写作端点（薄壳编排层）

资源边界：
  - 本模块负责「写前预警 → 起笔 → 自动质检 → 未达标则重写 → 循环」的全链路编排。
  - 单次起笔/续写（无循环）仍走 draft_routes.draft-assist/stream。
  - 质检逻辑复用 AIService.quality_check；存库逻辑内联（避免额外 HTTP 跳转）。
  - 辅助函数已拆分到：
      gated_draft_helpers.py  — 上下文构建 / 存库 / 预警格式化
      gated_draft_quality.py  — 质检内联执行 / 门槛判断 / 重写 prompt 构建

SSE 协议（JSON lines，prefix: ``data: ``）：
  gate_config       — 循环开始前推送生效配置（含 block_on_consistency_issues、hook_mandate_active 等）
  pre_warn_running  — 写前预警开始（每次起笔必跑）
  pre_warn_done     — 写前预警完成，附 risk_count / ok / protagonist_fact_sheet / writing_brief
  attempt_start     — 本轮起笔开始（strategy: initial | patch | full_rewrite）
  text              — 正文片段（与普通 draft-assist 格式完全一致）
  attempt_done      — 本轮起笔结束，附字数
  qc_running        — 质检开始
  qc_result         — 质检结果（passed / score / subscribe_intent / suggestions）
  gate_passed       — 达标，循环结束
  rewrite_queued    — 未达标，即将进行下一轮（附策略）
  gate_failed       — 达到最大次数仍未达标，章节置 needs_review
  error             — 不可恢复错误
  [DONE]            — 流结束标记
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, Project
from app.routers.ai.draft_routes import _build_draft_context
from app.routers.ai.pre_write_for_draft import resolve_pre_write_brief_for_draft
from app.routers.ai.draft_helpers import (
    hook_chapter_mandate_active,
    merge_writing_config,
    prewrite_gate_violation,
)
from app.routers.ai.gated_draft_helpers import (
    _build_location_context,
    _count_words_plain,
    _save_chapter_content,
)
from app.routers.ai.gated_draft_quality import (
    _build_rewrite_prompt,
    _check_passed,
    _run_quality_check_inline,
)
from app.routers.ai.schemas import GatedDraftRequest
from app.routers.ai.dabai_draft_handlers import (
    dabai_gated_draft_event_stream,
    should_route_dabai_draft,
)
from app.services.ai_service import AIService
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block

router = APIRouter()


@router.post("/gated-draft-stream")
async def gated_draft_stream(
    project_id: str,
    req: GatedDraftRequest,
    db: Session = Depends(get_db),
):
    """
    质量门控写作：写稿 → 自动质检 → 未达标则重写 → 循环至通过或暂停。

    流程：
    1. 读取 project.extra.writing_config 合并请求 override_config；构建起草上下文并执行写前硬门
       （``block_on_consistency_issues`` / ``block_on_realm_mismatch``），不通过则 ``409``。
    2. 循环（最多 max_rewrite_attempts 次）：
       a. 起笔（第1轮=initial，第2轮=patch，第3轮=full_rewrite）
       b. 保存章节正文 + 创建 ChapterVersion 快照
       c. 内联质检（复用 AIService.quality_check）
       d. 检查 overall_score、subscribe_intent；若开启 ``enforce_face_slap_payoff_when_hook_required``
          且本章为爽点结算章，则额外检查 face_slap_payoff 维度
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

    if req.replace_existing:
        from app.routers.chapters import clear_chapter_rewrite_derivatives

        clear_chapter_rewrite_derivatives(db, project_id, str(req.chapter_id))
        db.commit()
        db.refresh(chapter)

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    user_prompt_str = (req.user_prompt or "").strip()

    if should_route_dabai_draft(project):
        async def dabai_gated_stream():
            async for line in dabai_gated_draft_event_stream(
                db,
                svc,
                project,
                chapter,
                str(project_id),
                user_prompt=user_prompt_str,
                stream_log_ctx={
                    "project_id": str(project_id),
                    "chapter_id": str(req.chapter_id),
                },
            ):
                yield line

        return StreamingResponse(
            dabai_gated_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    cfg = merge_writing_config(project, req.override_config)

    try:
        draft_ctx = await _build_draft_context(db, project_id, chapter, project)
        rag_snapshot = draft_ctx.pop("rag_retrieval_snapshot", None)
        rag_log_id = draft_ctx.pop("rag_retrieval_log_id", None)
        db.commit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上下文构建失败：{e}") from e

    # 空间连续性约束块：注入写章 prompt，防止 AI 跨章位置漂移
    location_context = _build_location_context(db, str(project_id))

    viol = prewrite_gate_violation(
        db, project, chapter, draft_ctx, cfg, req.consistency_issue_ack,
    )
    if viol:
        raise HTTPException(status_code=409, detail=viol)

    hook_mandate = hook_chapter_mandate_active(draft_ctx, chapter)

    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def event_stream() -> AsyncGenerator[str, None]:
        if rag_snapshot:
            yield _sse(rag_snapshot)
        # 推送生效配置
        yield _sse({
            "event": "gate_config",
            "min_overall_score": cfg["min_overall_score"],
            "min_subscribe_intent": cfg["min_subscribe_intent"],
            "max_rewrite_attempts": cfg["max_rewrite_attempts"],
            "auto_quality_gate": cfg["auto_quality_gate"],
            "pre_write_warning_enabled": cfg["pre_write_warning_enabled"],
            "block_on_consistency_issues": cfg.get("block_on_consistency_issues", False),
            "consistency_block_severities": cfg.get("consistency_block_severities", ["high"]),
            "block_on_realm_mismatch": cfg.get("block_on_realm_mismatch", False),
            "enforce_face_slap_payoff_when_hook_required": cfg.get(
                "enforce_face_slap_payoff_when_hook_required", False
            ),
            "min_face_slap_payoff_score": cfg.get("min_face_slap_payoff_score", 6.0),
            "hook_mandate_active": hook_mandate,
        })

        user_prompt_str = (req.user_prompt or "").strip()
        last_qc: dict | None = None
        passed = False
        # 跨轮复用上下文：多轮间项目静态数据/上一章状态/承诺/伏笔/质检债务全部不变；
        # 而 gated 始终 replace_existing=True，draft_assist_stream 内部不读 existing_content。
        # 在路由层预先构建 draft_ctx，与写前硬门（一致性/境界）共用同一份上下文。

        # ── 写前预警（每次起笔必跑；整章重写时优先复用落库记录）──
        # 将预警结果格式化为「写前简报」块，通过 draft_assist_stream 的专属参数
        # pre_write_brief 注入（独立 2500 字预算），不拼入 user_prompt（上限 800 字）。
        # user_prompt_str 只保留用户/作者的补充指令，保持语义干净。
        # 后续重写轮仍沿用同一份 pre_warn_brief_block（状态锁定在整轮写作期间不变）。
        db.refresh(chapter)
        pre_warn_brief_block, pre_warn_events = await resolve_pre_write_brief_for_draft(
            db,
            chapter=chapter,
            project=project,
            project_id=str(project_id),
            svc=svc,
            model_profile=req.model_profile or "local",
            llm_provider_id=str(req.llm_provider_id) if req.llm_provider_id else None,
            persist_record=True,
            reuse_if_exists=bool(req.replace_existing),
        )
        for payload in pre_warn_events:
            yield _sse(payload)

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

            # ── 刷新章节实体（保存正文用，仍每轮做）；上下文复用路由层预构建的 draft_ctx ──
            db.refresh(chapter)

            accumulated = ""
            try:
                async for chunk in svc.draft_assist_stream(
                    **draft_ctx,
                    user_prompt=current_user_prompt,
                    # 写前简报走独立通道（2500 字预算），不与 user_prompt 竞争截断配额；
                    # 重写轮沿用首轮生成的同一份简报，保持状态锁定在整轮写作期间一致。
                    pre_write_brief=pre_warn_brief_block,
                    # 空间连续性约束：各章复用同一份（角色位置在整轮写作期间不变）
                    location_context=location_context,
                    replace_existing=True,  # 门控写作始终整章重写
                    stream_log_context={
                        "project_id": str(project_id),
                        "chapter_id": str(req.chapter_id),
                        "gated_attempt": attempt,
                        "rag_retrieval_log_id": rag_log_id,
                    },
                ):
                    accumulated += chunk
                    yield _sse({"text": chunk})
            except Exception as e:
                yield _sse({"error": f"起笔失败（第{attempt}轮）：{e}"})
                return

            # P2.5: 推送本轮截断警告（如有）
            attempt_warnings = getattr(svc, "_truncation_warnings", None) or []
            if attempt_warnings:
                yield _sse({
                    "event": "truncation_warning",
                    "attempt": attempt,
                    "warnings": list(attempt_warnings),
                })

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
            ok, failing = _check_passed(qc, cfg, hook_mandate_active=hook_mandate)
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
