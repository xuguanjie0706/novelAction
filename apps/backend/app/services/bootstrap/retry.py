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
    """调用 AI；失败时做一次外层补偿重试（间隔退避），避免与 ``_call_ai`` 内层重试叠加失控。"""
    last_err: BaseException | None = None
    outer_delays = (3.0,)
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
            if attempt < len(outer_delays):
                await asyncio.sleep(outer_delays[attempt])
            continue
    assert last_err is not None
    raise last_err
