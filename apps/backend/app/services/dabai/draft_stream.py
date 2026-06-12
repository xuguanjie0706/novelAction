"""dabai 主链路流式写章 — 轻量 prompt，不注入通用写作巨 prompt。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncGenerator

from sqlalchemy.orm import Session

from app.models import Chapter, OutlineNode, Project
from app.services.ai.service import AIService
from app.services.dabai.draft_context import DabaiDraftContext, build_dabai_draft_context
from app.services.dabai.draft_prompt import build_dabai_draft_prompt
from app.services.dabai.outline_plan import resolve_chapter_plan
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block
from app.routers.ai.text_utils import plain_text, strip_tail_meta_lines


@dataclass
class DabaiDraftInputs:
    """写章前置数据（章纲/上章尾/上下文块）。

    写前导演单与正文生成共用同一份，避免重复查库/检索；
    由 ``prepare_dabai_draft_inputs`` 组装。
    """

    plan: OutlineNode | None
    prev_tail: str
    context: DabaiDraftContext


async def prepare_dabai_draft_inputs(
    db: Session,
    project: Project,
    chapter: Chapter,
    project_id: str,
) -> DabaiDraftInputs:
    """组装写章前置数据（供导演单 + 正文生成两段共用）。"""
    plan = resolve_chapter_plan(db, project_id, chapter)
    prev_tail = _prev_chapter_tail(db, project_id, chapter) if (chapter.sort_order or 0) > 0 else ""
    draft_ctx = await build_dabai_draft_context(db, project, chapter, plan)
    return DabaiDraftInputs(plan=plan, prev_tail=prev_tail, context=draft_ctx)


def _prev_chapter_tail(db: Session, project_id: str, chapter: Chapter) -> str:
    from app.models import Chapter as Ch

    prev = (
        db.query(Ch)
        .filter(
            Ch.project_id == project_id,
            Ch.sort_order == (chapter.sort_order or 0) - 1,
        )
        .first()
    )
    if not prev or not prev.content:
        return ""
    prev_plain = plain_text(prev.content)
    body, _ = split_plain_manuscript_and_index_block(prev_plain)
    base = body.strip() if body.strip() else prev_plain
    clean = strip_tail_meta_lines(base)
    return clean[-800:] if len(clean) > 800 else clean


def dabai_draft_max_tokens(expected_words: int) -> int:
    """dabai 正文 completion 预算：对齐 prompt 字数上限（目标+200），避免失控超长。"""
    from app.services.llm_token_budgets import ensure_min_completion_tokens

    target = int(expected_words or 2000)
    hi = target + 200
    cap = max(1600, int(hi * 1.08))
    return min(ensure_min_completion_tokens(cap), 4096)


async def stream_dabai_chapter_draft(
    svc: AIService,
    db: Session,
    project: Project,
    chapter: Chapter,
    *,
    project_id: str,
    user_prompt: str = "",
    replace_existing: bool = False,
    stream_log_context: dict | None = None,
    inputs: DabaiDraftInputs | None = None,
    pre_warn_block: str = "",
) -> AsyncGenerator[str, None]:
    """流式生成 dabai 正文（纯文本 chunk）。

    上下文：图谱主角状态 + 近章前情 + pgvector 记忆 + 出场人物状态 + 上章结尾，
    由 ``build_dabai_draft_context`` 组装（各源独立降级，不阻塞写章）。

    Args:
        inputs: 预组装的前置数据（路由层跑完导演单后传入复用）；None 时自行组装。
        pre_warn_block: 写前导演单注入块（空串 = 无简报降级路径）。
    """
    if inputs is None:
        inputs = await prepare_dabai_draft_inputs(db, project, chapter, project_id)
    plan = inputs.plan
    expected = int((plan.expected_words if plan else None) or 2000)

    system, prompt = build_dabai_draft_prompt(
        project,
        chapter,
        plan,
        prev_chapter_tail=inputs.prev_tail,
        user_prompt=user_prompt,
        replace_existing=replace_existing,
        context=inputs.context,
        pre_warn_block=pre_warn_block,
    )
    ctx = {"operation": "dabai_draft_stream", "bootstrap_mode": "dabai"}
    if stream_log_context:
        ctx.update(stream_log_context)

    async for chunk in svc._stream_ai(
        system,
        prompt,
        task="dabai.write",
        max_tokens=dabai_draft_max_tokens(expected),
        context=ctx,
    ):
        if chunk:
            yield chunk
