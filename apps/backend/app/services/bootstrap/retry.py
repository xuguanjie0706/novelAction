"""Bootstrap 步骤共用的 LLM 调用入口。

设计决策（2026-06）：去掉 Bootstrap 外层网络退避重试。
    经验上，立项会议等步骤一旦因服务/限流首次失败，紧接着的退避重试大多同样失败，
    只会拖长用户等待并放大成本。改为「首次失败即抛错」，由步骤级 interrupt
    （``pause_for_step_retry``）让用户决定是否手动重试该步。
    注意：这里去掉的只是 Bootstrap 这一外层；``_call_ai`` 内部（AIService 全局层，
    写章/质检共用）的短退避不在本次范围内，保持不变。
    各步骤内部的「格式校验重试」（``for attempt in range(N)``，坏 JSON 重提示）亦保留。
"""

from __future__ import annotations

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
    """调用 AI，单次执行；失败立即抛错（不再做外层退避重试）。

    函数名与签名保持不变以兼容全部调用方（``svc._call_with_retry`` 及各 step）。
    """
    return await ai._call_ai(
        system,
        prompt,
        max_tokens=max_tokens,
        task=task,
    )
