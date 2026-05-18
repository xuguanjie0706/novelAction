"""AUTO-GENERATED mixin chunk from legacy ai_service — see package docstring."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import List, AsyncGenerator, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from app.config import settings
from app.services.llm_config import normalize_openai_base_url, resolve_gemini_connection
from app.services.llm_task_profiles import resolve_task_profile
from app.services.llm_token_budgets import (
    max_tokens_auto_debrief,
    max_tokens_chapter_quality_check,
    max_tokens_coherence_apply,
    max_tokens_coherence_check,
    max_tokens_draft_stream,
    max_tokens_expand_outline,
    max_tokens_extract_memory,
    max_tokens_outline_quality_check,
    max_tokens_plan_full_structure,
    max_tokens_quality_micro_patch,
    max_tokens_suggest_stream,
)
from app.services.llm_call_log import log_llm_call
from app.services.genre_kit import get_genre_guardrail, normalize_genre
from app.services.xuanhuan_lexicon import (
    format_modern_blacklist_for_prompt,
    is_xuanhuan_like_genre,
)
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block


class ChatMixin:
    async def suggest_stream(
        self,
        chapter_content: str,
        user_prompt: str,
        rag_context: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        AI 写作建议流（SSE）。

        Args:
            chapter_content: 当前章节正文（取前 1500 字注入 prompt）。
            user_prompt: 作者的具体问题或修改意图。
            rag_context: 由路由层组装的 RAG 上下文块，包含语义相关记忆、
                         未收束伏笔、人物状态等；空字符串表示无上下文可用。
        """
        system = "你是经验丰富的网络小说写作顾问，帮助作者优化章节内容。"

        rag_block = (
            f"\n\n【相关上下文（供参考，不要在回答中复述这些内容）】\n{rag_context}"
            if rag_context.strip()
            else ""
        )

        prompt = f"""当前章节内容（前1500字）：
{chapter_content[:1500]}
{rag_block}

作者问题：{user_prompt}

请给出具体的修改建议和示例。"""

        async for chunk in self._stream_ai(
            system,
            prompt,
            max_tokens=max_tokens_suggest_stream(self.profile),
            context={"operation": "suggest_stream"},
            task="suggest.stream",
        ):
            yield chunk

    # ── 持久化对话 ───────────────────────────────────
    async def chat_stream(
        self,
        user_prompt: str,
        context_label: str,
        context_text: str,
        chat_history: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        system = (
            "你是小说创作系统里的对话助手，回答必须基于用户当前打开的作品上下文。"
            "如果上下文不足，要明确说明缺失信息，并给出下一步可检查的位置。"
        )
        history_lines = []
        for item in (chat_history or [])[-12:]:
            role = "作者" if item.get("role") == "user" else "AI助手"
            content = str(item.get("content") or "").strip()
            if content:
                history_lines.append(f"{role}：{content[:1200]}")

        context_limit = 50000 if self.profile == "gemini" else 8000
        prompt = f"""【当前对话上下文：{context_label}】
{self._clip_context(context_text, 2000, context_limit) or '（未提供）'}

【最近对话】
{chr(10).join(history_lines) or '（暂无）'}

【作者问题】
{user_prompt}

请像可以连续追问的写作搭档一样回答：
1. 先直接回答问题，不要泛泛提供写作建议。
2. 引用大纲/正文/设定中的具体依据。
3. 如果用户问“怎么突破/为何如此/前后是否矛盾”，优先从当前上下文抽取因果链。
4. 不要把左侧导航菜单、按钮名称当作小说内容。
"""

        async for chunk in self._stream_ai(
            system,
            prompt,
            max_tokens=max_tokens_suggest_stream(self.profile),
            context={"operation": "chat_stream"},
            task="suggest.stream",
        ):
            yield chunk

    # ── 记忆提取 ──────────────────────────────────────
