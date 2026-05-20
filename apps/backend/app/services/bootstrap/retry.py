"""Bootstrap 步骤共用的 LLM 外层重试（与 AIService 内层退避互补）。"""

from __future__ import annotations

import asyncio
from typing import Optional

from app.services.ai_service import AIService


async def call_with_retry(
    ai: AIService,
    system: str,
    prompt: str,
    *,
    max_tokens: int = 2048,
    task: Optional[str] = None,
) -> str:
    """调用 AI；可重试错误时外层退避重试（与 ``_call_ai`` 内层短退避互补）。"""
    last_err: BaseException | None = None
    outer_delays = (2.0, 5.0, 10.0)
    for attempt in range(len(outer_delays) + 1):
        try:
            return await ai._call_ai(
                system,
                prompt,
                max_tokens=max_tokens,
                task=task,
            )
        except Exception as e:
            last_err = e
            if attempt >= len(outer_delays):
                break
            if not ai._is_retryable_llm_error(e):
                break
            await asyncio.sleep(outer_delays[attempt])
    assert last_err is not None
    raise last_err
