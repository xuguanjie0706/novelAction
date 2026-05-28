"""按卷懒展开章纲：POST /outline/volumes/{volume_node_id}/expand-chapters（SSE）。

设计要点
--------
- 每次调用只展开**一个**卷，不批量。
- 注入三类已写上下文（章节摘要 / 未兑现承诺 / 记忆片段），让 AI 感知当前故事状态。
- 幂等保护：若目标卷已有 chapter_plan 子节点且未传 force=true，返回 409。
- SSE 事件序列：step_start → step_done / error → end。
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import asc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, MemoryChunk, OutlineNode, Project, ReaderPromise
from app.services.bootstrap.context_vol_expand import build_vol_expand_ctx
from app.services.bootstrap.chapter_plan_batches import normalize_volume_planned_chapters
from app.services.bootstrap.retry import call_with_retry
from app.services.bootstrap.steps.vol_chapter_plans import gen_vol_chapter_plans

router = APIRouter()


# ── 请求体 ────────────────────────────────────────────────────────────────────

class VolExpandRequest(BaseModel):
    """按卷展开章纲的请求参数。

    Attributes:
        model_profile: AI 线路标识（local / gemini / 或 llm_provider_id 字符串）。
        llm_provider_id: 若使用管理后台配置的远程模型，传对应行的 UUID；否则传 None。
        force: 为 True 时允许覆盖已有章节计划（会先删旧节点再重新生成）。
        written_context_limit: 注入的已写章节摘要条数上限（默认 15）。
        memory_limit: 注入的记忆片段条数上限（默认 10）。
        promise_limit: 注入的未兑现承诺条数上限（默认 8）。
    """

    model_profile: str = "local"
    llm_provider_id: str | None = None
    force: bool = False
    written_context_limit: int = 15
    memory_limit: int = 10
    promise_limit: int = 8


# ── 辅助：薄壳 svc 对象 ───────────────────────────────────────────────────────

class _BootstrapSvc:
    """最小化 svc 鸭子类型，供 gen_vol_chapter_plans 调用。

    gen_vol_chapter_plans 只需要：
    - svc._call_with_retry(system, prompt, task=..., max_tokens=...)
    - svc.db  （用于 db.add / db.commit）

    不依赖完整 GenerationService，避免额外的初始化开销。
    """

    def __init__(self, ai: Any, db: Session) -> None:
        self._ai = ai
        self.db = db

    async def _call_with_retry(
        self,
        system: str,
        prompt: str,
        *,
        task: str | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """委托给 bootstrap retry 模块的外层重试逻辑。"""
        return await call_with_retry(
            self._ai,
            system,
            prompt,
            max_tokens=max_tokens,
            task=task,
        )


# ── 辅助：查询已写上下文 ──────────────────────────────────────────────────────

def _get_written_summaries(db: Session, project_id: str, limit: int) -> list[str]:
    """取已完成章节的摘要列表（优先用 extra.core_event，回退 title）。

    Args:
        db:         数据库会话。
        project_id: 项目 UUID 字符串。
        limit:      最多取多少条，避免 prompt 膨胀。

    Returns:
        摘要字符串列表，按章节排序。
    """
    chapters = (
        db.query(Chapter)
        .filter(
            Chapter.project_id == project_id,
            Chapter.deleted_at.is_(None),
        )
        .order_by(asc(Chapter.sort_order))
        .limit(limit)
        .all()
    )
    summaries: list[str] = []
    for ch in chapters:
        extra = ch.extra or {}
        # 优先用 debrief 阶段写入的核心事件摘要
        core = (
            extra.get("core_event")
            or extra.get("debrief_summary")
            or extra.get("summary")
        )
        summaries.append(core or ch.title)
    return summaries


def _get_open_promises(db: Session, project_id: str, limit: int) -> list[dict]:
    """取未兑现的 ReaderPromise，按优先级降序。

    Args:
        db:         数据库会话。
        project_id: 项目 UUID 字符串。
        limit:      最多取多少条。

    Returns:
        字典列表，含 promise_text / promise_type / priority 字段。
    """
    rows = (
        db.query(ReaderPromise)
        .filter(
            ReaderPromise.project_id == project_id,
            ReaderPromise.status == "open",
        )
        .order_by(ReaderPromise.priority.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "promise_text": r.promise_text,
            "promise_type": r.promise_type,
            "priority": r.priority,
        }
        for r in rows
    ]


def _get_memory_chunks(db: Session, project_id: str, limit: int) -> list[str]:
    """取最近的 MemoryChunk 内容列表。

    优先选 memory_type 为 foreshadow / character_state / conflict 的条目，
    这三类对章纲生成的约束价值最高。

    Args:
        db:         数据库会话。
        project_id: 项目 UUID 字符串。
        limit:      最多取多少条。

    Returns:
        MemoryChunk.content 字符串列表。
    """
    # 优先级类型先取，再补 event 类型填满配额
    priority_types = ("foreshadow", "character_state", "conflict")
    chunks: list[str] = []

    for mtype in priority_types:
        if len(chunks) >= limit:
            break
        rows = (
            db.query(MemoryChunk)
            .filter(
                MemoryChunk.project_id == project_id,
                MemoryChunk.memory_type == mtype,
            )
            .order_by(MemoryChunk.created_at.desc())
            .limit(limit - len(chunks))
            .all()
        )
        chunks.extend(r.content for r in rows if r.content)

    if len(chunks) < limit:
        remaining = limit - len(chunks)
        rows = (
            db.query(MemoryChunk)
            .filter(
                MemoryChunk.project_id == project_id,
                MemoryChunk.memory_type == "event",
            )
            .order_by(MemoryChunk.created_at.desc())
            .limit(remaining)
            .all()
        )
        chunks.extend(r.content for r in rows if r.content)

    return chunks


# ── SSE 事件发射器 ────────────────────────────────────────────────────────────

def _sse(event: str, **kwargs) -> str:
    """序列化为 SSE data 行。"""
    return f"data: {json.dumps({'event': event, **kwargs}, ensure_ascii=False)}\n\n"


def _format_vol_expand_failure(errors: list[str]) -> str:
    """将批次 AI 失败原因转为用户可读提示（优先识别鉴权/拦截类根因）。"""
    if not errors:
        return (
            "AI 未返回有效章纲。请在大纲页顶部检查「模型线路」与 API Key 是否有效，"
            "或到管理后台更新 LlmProvider 后重试。"
        )
    joined = " ".join(errors).lower()
    if "invalid token" in joined or "401" in joined:
        return (
            "模型 API Key 无效或已过期（401）。请在管理后台更新对应线路的 api_key，"
            "或在大纲页切换到其他模型线路后重试。"
        )
    if "blocked" in joined or "permissiondenied" in joined:
        blocked_batches = [
            e for e in errors if "blocked" in e.lower() or "permissiondenied" in e.lower()
        ]
        detail = blocked_batches[-1] if blocked_batches else errors[-1]
        return (
            "模型请求被服务商拦截（Your request was blocked）。"
            "常见原因：当前线路触发了内容安全策略、账号额度或代理网关限制。"
            "请在大纲页切换到其他线路（如 Kimi / 豆包），或在管理后台更换 api_key 后重试。"
            f" 详情：{detail}"
        )
    if any("未返回可解析" in e for e in errors):
        parse_errs = [e for e in errors if "未返回可解析" in e]
        return (
            "模型返回了内容但无法解析为章纲 JSON（可能输出被截断或格式不符）。"
            "可尝试：换更大上下文的模型、在 .env 提高 VOL_EXPAND_CHAPTERS_MAX_TOKENS，或重新生成。"
            f" 详情：{parse_errs[-1]}"
        )
    last = errors[-1]
    if len(last) > 220:
        return f"章纲生成失败：{last[:220]}…"
    return f"章纲生成失败：{last}"


# ── 主路由 ────────────────────────────────────────────────────────────────────

@router.post("/volumes/{volume_node_id}/expand-chapters")
async def expand_volume_chapters(
    project_id: str,
    volume_node_id: str,
    req: VolExpandRequest,
    db: Session = Depends(get_db),
):
    """为指定卷懒展开章节计划（SSE 流式）。

    流程：
    1. 验证 volume_node 存在且 node_type == "volume"。
    2. 幂等检查：已有 chapter_plan 子节点且 force=False → 409。
    3. force=True 时先删除旧 chapter_plan 子节点。
    4. 查询已写章节摘要、未兑现承诺、记忆片段，构建上下文。
    5. 调用 gen_vol_chapter_plans，写库。
    6. SSE 推送 step_start / step_done / error / end。

    Args:
        project_id:     路径参数，项目 UUID。
        volume_node_id: 路径参数，目标卷 OutlineNode UUID。
        req:            请求体，含 model_profile / force 等参数。
        db:             数据库会话（依赖注入）。

    Returns:
        StreamingResponse（text/event-stream）。

    Raises:
        HTTPException 404: 项目或卷节点不存在。
        HTTPException 422: 节点不是 volume 类型。
        HTTPException 409: 已有章节计划且 force=False。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    volume_node = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.id == volume_node_id,
            OutlineNode.project_id == project_id,
        )
        .first()
    )
    if not volume_node:
        raise HTTPException(404, "Volume node not found")
    if volume_node.node_type != "volume":
        raise HTTPException(422, f"节点类型必须为 volume，当前为 {volume_node.node_type!r}")

    # 幂等检查
    existing = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.parent_id == volume_node_id,
            OutlineNode.node_type == "chapter_plan",
        )
        .count()
    )
    if existing > 0 and not req.force:
        raise HTTPException(
            409,
            f"该卷已有 {existing} 个章节计划。若要重新生成，请传 force=true。",
        )
    if existing > 0 and req.force:
        # 删除旧节点再重新生成
        db.query(OutlineNode).filter(
            OutlineNode.parent_id == volume_node_id,
            OutlineNode.node_type == "chapter_plan",
        ).delete(synchronize_session=False)
        db.commit()

    async def stream() -> AsyncIterator[str]:
        yield _sse("step_start", step="expand_chapters", volume_title=volume_node.title)

        try:
            # ── 构建总编辑级富上下文 ──────────────────────────────────────
            # build_vol_expand_ctx 一次性查询所有需要的数据库表，返回：
            # - ctx: 含 char_profiles / storyline_ids / positioning 等30+字段
            # - editorial_prompt_block: 立项定位/卡司档案/关系台账/伏笔台账等结构化块
            ctx, editorial_prompt_block = build_vol_expand_ctx(db, project, volume_node)

            # ── 查询动态上下文（已写章节摘要、记忆片段）─────────────────
            written_summaries = _get_written_summaries(
                db, project_id, req.written_context_limit
            )
            memory_chunks = _get_memory_chunks(db, project_id, req.memory_limit)
            # open_promises 已在 editorial_prompt_block 里结构化呈现，此处仍查以备用
            open_promises = _get_open_promises(db, project_id, req.promise_limit)

            yield _sse(
                "context_ready",
                written_count=len(written_summaries),
                promise_count=len(open_promises),
                memory_count=len(memory_chunks),
                editorial_blocks=editorial_prompt_block.count("\n【"),
            )

            # ── 初始化 AI + svc 薄壳 ──────────────────────────────────────
            from app.services.ai_service import AIService

            ai = AIService(
                profile=req.model_profile,
                db=db,
                llm_provider_id=req.llm_provider_id,
            )
            svc = _BootstrapSvc(ai=ai, db=db)

            # ── 调用生成 ───────────────────────────────────────────────────
            nodes = await gen_vol_chapter_plans(
                svc=svc,
                project=project,
                volume_node=volume_node,
                ctx=ctx,
                written_summaries=written_summaries,
                open_promises=open_promises,
                memory_chunks=memory_chunks,
                editorial_prompt_block=editorial_prompt_block,
            )

            db.refresh(volume_node)
            vol_extra = volume_node.extra or {}
            linter_summary = vol_extra.get("linter_summary") or {}

            blocked = bool(vol_extra.get("linter_blocked"))
            block_msg = str(vol_extra.get("linter_user_message") or "").strip()
            if blocked and not block_msg:
                from app.services.outline_linter.user_facing import build_linter_block_payload

                block_msg = build_linter_block_payload(
                    {
                        "status": vol_extra.get("linter_status", "failed"),
                        "issue_count": linter_summary.get("issue_count", 0),
                        "critical_count": linter_summary.get("critical_count", 0),
                        "high_count": linter_summary.get("high_count", 0),
                        "issues": vol_extra.get("linter_issues") or [],
                    },
                    chapter_count=len(nodes),
                ).get("linter_message", "")
            generation_failed = len(nodes) == 0 and not blocked
            gen_error = (
                _format_vol_expand_failure(ctx.get("vol_chapter_batch_errors") or [])
                if generation_failed
                else None
            )
            planned_count = normalize_volume_planned_chapters(
                (volume_node.extra or {}).get("planned_chapters", 30)
            )
            chapter_incomplete = 0 < len(nodes) < planned_count
            yield _sse(
                "step_done",
                step="expand_chapters",
                volume_title=volume_node.title,
                chapter_count=len(nodes),
                planned_chapter_count=planned_count,
                chapter_incomplete=chapter_incomplete,
                linter_status=vol_extra.get("linter_status", "ok"),
                linter_issue_count=linter_summary.get("issue_count", 0),
                linter_critical_count=linter_summary.get("critical_count", 0),
                linter_high_count=linter_summary.get("high_count", 0),
                linter_blocked=blocked,
                linter_message=block_msg or None,
                generation_failed=generation_failed,
                generation_error=gen_error,
            )
            if generation_failed and gen_error:
                yield _sse("error", step="expand_chapters", message=gen_error)
            elif chapter_incomplete:
                yield _sse(
                    "error",
                    step="expand_chapters",
                    message=(
                        f"章纲不完整：计划 {planned_count} 章，实际生成 {len(nodes)} 章。"
                        "请换更大上下文模型或提高 VOL_EXPAND_CHAPTERS_MAX_TOKENS 后 force 重试。"
                    ),
                )
            elif blocked and block_msg:
                yield _sse("error", step="expand_chapters", message=block_msg)

        except Exception as exc:  # noqa: BLE001
            yield _sse("error", step="expand_chapters", message=str(exc))

        yield _sse("end")

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
