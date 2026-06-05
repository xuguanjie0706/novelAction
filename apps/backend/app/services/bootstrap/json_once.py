"""Bootstrap 单轮 LLM + JSON 校验；失败立即抛错，不做格式重试。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

ValidateFn = Callable[[Any], str | None]


class BootstrapStepError(RuntimeError):
    """Bootstrap 步骤失败；``str(exc)`` 为 ``[步骤名] 原因``。"""

    def __init__(self, step: str, reason: str) -> None:
        self.step = step
        self.reason = reason
        super().__init__(f"[{step}] {reason}")


async def call_bootstrap_json_once(
    svc: Any,
    *,
    step: str,
    system: str,
    prompt: str,
    task: str,
    validate: ValidateFn,
) -> Any:
    """调用模型一次；解析 JSON 后执行 ``validate``，失败则 ``BootstrapStepError``。"""
    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task=task,
    )
    try:
        data = parse_json(raw)
    except Exception as exc:
        raise BootstrapStepError(step, f"JSON 解析失败：{exc}") from exc
    err = validate(data)
    if err:
        raise BootstrapStepError(step, err)
    return data
