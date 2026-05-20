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


class MemoryMixin:
    async def extract_memory(
        self,
        chapter_content: str,
        chapter_title: str,
        chapter_number: int,
    ) -> List[dict]:
        system = """你是小说记忆提取助手。从章节中提取关键记忆条目，严格返回 JSON 数组。"""
        prompt = f"""从以下章节提取关键记忆条目（最多8条），返回 JSON 数组：

章节{chapter_number}《{chapter_title}》正文：
{chapter_content[:3000]}

返回格式：
[
  {{
    "memory_type": "event",
    "title": "林默获得古传承",
    "content": "林默在鬼门关意外触发古老传承，获得...",
    "tags": ["林默", "传承", "关键事件"],
    "importance_score": 0.9
  }},
  ...
]

importance_score 评分规则（0.0-1.0）：
- 0.9-1.0：影响主线走向、人物生死、重要伏笔兑现
- 0.6-0.8：角色状态重大变化、关键道具获取/丢失、势力变化
- 0.3-0.5：普通事件、次要角色互动、背景信息
- 0.0-0.2：可省略的细节、重复描述

memory_type 只能是: event / character_state / foreshadow / setting / conflict
"""
        response = await self._call_ai(
            system,
            prompt,
            max_tokens=max_tokens_extract_memory(self.profile),
            context={"operation": "extract_memory", "chapter_title": chapter_title},
            task="debrief.extract_memory",
        )
        try:
            text = response.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception:
            return []

    # ── 大纲展开（五要素卡片）─────────────────────────
