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


class ClientMixin:
    def _large_context_enabled(self) -> bool:
        return self.profile == "gemini"

    def _clip_context(
        self,
        text: str | None,
        local_limit: int,
        large_limit: int | None,
        from_end: bool = False,
        field_name: str = "",
    ) -> str:
        """裁剪上下文。large_limit=None 表示大上下文模型（Gemini）不截断。
        真正发生截断时记录 warning，并在 self._truncation_warnings 追加提示。
        """
        clean = (text or "").strip()
        if not clean:
            return ""
        if self._large_context_enabled():
            if large_limit is None:
                return clean  # Gemini：不截断
            limit = large_limit
        else:
            limit = local_limit
        if len(clean) <= limit:
            return clean
        label = f"[{field_name}] " if field_name else ""
        logger.warning(
            "⚠️ 上下文截断 %sprofile=%s limit=%d original_len=%d",
            label, self.profile, limit, len(clean),
        )
        self._truncation_warnings.append(
            f"字段 {field_name or '未知'} 被截断：原始长度 {len(clean)} 字符，限制 {limit} 字符"
        )
        return clean[-limit:] if from_end else clean[:limit]

    def _plain_text(self, content: str | None) -> str:
        return re.sub(r"<[^>]+>", "", content or "").strip()

    def _get_client(self):
        """
        始终使用 AsyncOpenAI，通过 base_url + api_key 指向任意 OpenAI 兼容服务（由 profile 与配置决定，无固定厂商）
        """
        if self._gemini_unconfigured:
            raise RuntimeError(
                "未配置远程大模型：请在管理后台「大模型」中新增并启用/设为默认，"
                "或设置环境变量 GEMINI_BASE_URL 与 GEMINI_MODEL"
            )
        if self.profile == "default" and not (self.model or "").strip():
            raise RuntimeError(
                "未配置本地模型：请在 apps/backend/.env 设置 AI_MODEL（OpenAI 兼容的模型 id），"
                "或在前端顶部「模型 / 线路」中选择已启用的远程线路。"
            )
        if self._client:
            return self._client
        import httpx
        import openai

        timeout = httpx.Timeout(
            connect=settings.LLM_HTTP_CONNECT_TIMEOUT,
            read=settings.LLM_HTTP_READ_TIMEOUT,
            write=120.0,
            pool=30.0,
        )
        self._client = openai.AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=timeout,
        )
        return self._client

