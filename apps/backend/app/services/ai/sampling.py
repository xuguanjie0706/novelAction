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
    ensure_min_completion_tokens,
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
    min_completion_tokens,
)
from app.services.llm_billing_context import resolve_llm_billing_user_id
from app.services.llm_errors import is_retryable_llm_error
from app.services.llm_call_log import log_llm_call, merge_truncation_into_context
from app.services.ai.llm_response_text import message_completion_text
from app.services.genre_kit import get_genre_guardrail, normalize_genre
from app.services.xuanhuan_lexicon import (
    format_modern_blacklist_for_prompt,
    is_xuanhuan_like_genre,
)
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block


class SamplingMixin:
    def _log_context_payload(self, context: Optional[dict], task: Optional[str], sampling_kwargs: dict) -> dict:
        """组装写入 ``llm_call_logs.context`` 的元数据（含截断警告）。"""
        base = {**(context or {}), "task": task, "sampling": sampling_kwargs}
        warnings = getattr(self, "_truncation_warnings", None) or []
        return merge_truncation_into_context(base, warnings)

    def _preflight_credit_check(self) -> None:
        """积分预检：余额 ≤ 0 阻断；余额 > 0 允许（含最后一次透支扣费）。

        ``CREDIT_ENFORCEMENT=off`` 时跳过（开发模式）。

        Raises:
            HTTPException 402: 余额 ≤ 0 时。
        """
        from app.services import credit_service  # 延迟导入，避免循环依赖

        uid = resolve_llm_billing_user_id(getattr(self, "_user_id", None))
        credit_service.preflight_billed_call(uid, db=self._db)

    def _is_retryable_llm_error(self, err: Exception) -> bool:
        return is_retryable_llm_error(err)

    def _build_sampling_kwargs(
        self,
        task: Optional[str],
        sampling_overrides: Optional[dict],
    ) -> dict:
        """合并「任务级默认采样」与「调用方覆写」并剔除空值。

        - `task`：在 ``llm_task_profiles.TASK_PROFILES`` 中查表，未命中返回空 dict；
        - `sampling_overrides`：调用方临时覆写（例如某次 A/B 测试），优先级最高；
        - 空 dict / None 字段会被剔除，避免网关因不识别的空字段报错。

        返回的 dict 直接展开进 ``client.chat.completions.create(**kwargs)``。
        """
        merged = dict(resolve_task_profile(task))
        if sampling_overrides:
            for k, v in sampling_overrides.items():
                if v is not None:
                    merged[k] = v
        return {k: v for k, v in merged.items() if v is not None}

    async def _call_ai(
        self,
        system: str,
        prompt: str,
        max_tokens: int | None = None,
        context: Optional[dict] = None,
        *,
        task: Optional[str] = None,
        sampling: Optional[dict] = None,
    ) -> str:
        """非流式 LLM 调用。

        Args:
            system: 系统提示。
            prompt: 用户提示。
            max_tokens: 单次输出上限。
            context: 写入 ``llm_call_logs.context`` 的对账元数据。
            task: 任务名，用于查 ``llm_task_profiles`` 选取采样参数；缺省走网关默认。
            sampling: 调用方临时覆写采样字段（temperature/top_p/...）。

        Returns:
            模型返回的纯文本内容（不含 ``<think>``）。
        """
        max_tokens = ensure_min_completion_tokens(
            max_tokens if max_tokens is not None else min_completion_tokens()
        )
        self._preflight_credit_check()
        client = self._get_client()
        start = time.perf_counter()
        sampling_kwargs = self._build_sampling_kwargs(task, sampling)
        try:
            # SDK 本身会重试；这里再补一层短退避，兜住网关偶发 5xx，减少工作流整体失败。
            resp = None
            last_error: Exception | None = None
            retry_delays = (0.8, 1.6)
            for attempt in range(len(retry_delays) + 1):
                try:
                    resp = await client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=max_tokens,
                        **sampling_kwargs,
                    )
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    if attempt >= len(retry_delays) or not self._is_retryable_llm_error(e):
                        raise
                    await asyncio.sleep(retry_delays[attempt])

            if resp is None:
                if last_error is not None:
                    raise last_error
                raise RuntimeError("LLM 调用失败：未获得响应")

            choices = getattr(resp, "choices", None) or []
            if not choices:
                raise RuntimeError("LLM 返回空 choices，无法读取正文")
            msg = getattr(choices[0], "message", None)
            content = message_completion_text(msg)
            if not content.strip():
                usage_obj = getattr(resp, "usage", None)
                comp_tok = getattr(usage_obj, "completion_tokens", None) if usage_obj else None
                raise RuntimeError(
                    "LLM 返回空正文"
                    + (f"（completion_tokens={comp_tok}，thinking 模型可能未输出可见 JSON）"
                       if comp_tok else "")
                )
            usage_obj = getattr(resp, "usage", None)
            usage = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", None),
                "completion_tokens": getattr(usage_obj, "completion_tokens", None),
                "total_tokens": getattr(usage_obj, "total_tokens", None),
            } if usage_obj is not None else {}
            log_llm_call(
                mode=self.profile,
                model=self.model,
                llm_endpoint=f"{self.base_url.rstrip('/')}/chat/completions",
                context=self._log_context_payload(context, task, sampling_kwargs),
                duration_ms=int((time.perf_counter() - start) * 1000),
                status="ok",
                prompt_text=f"{system}\n{prompt}",
                completion_text=content,
                usage=usage,
                input_payload={
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    **sampling_kwargs,
                },
                output_payload={"text": content},
                user_id=resolve_llm_billing_user_id(getattr(self, "_user_id", None)),
                task=task,
                tier_override=getattr(self, "_billing_tier", None),
                db=self._db,
            )
            return content
        except Exception as e:
            log_llm_call(
                mode=self.profile,
                model=self.model,
                llm_endpoint=f"{self.base_url.rstrip('/')}/chat/completions",
                context=self._log_context_payload(context, task, sampling_kwargs),
                duration_ms=int((time.perf_counter() - start) * 1000),
                status="error",
                prompt_text=f"{system}\n{prompt}",
                error=str(e),
                input_payload={
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    **sampling_kwargs,
                },
                user_id=resolve_llm_billing_user_id(getattr(self, "_user_id", None)),
                task=task,
                tier_override=getattr(self, "_billing_tier", None),
                db=self._db,
            )
            raise

    async def _stream_ai(
        self,
        system: str,
        prompt: str,
        max_tokens: int | None = None,
        context: Optional[dict] = None,
        *,
        task: Optional[str] = None,
        sampling: Optional[dict] = None,
    ) -> AsyncGenerator[str, None]:
        """流式 LLM 调用。参数语义与 :meth:`_call_ai` 一致。"""
        max_tokens = ensure_min_completion_tokens(
            max_tokens if max_tokens is not None else min_completion_tokens()
        )
        self._preflight_credit_check()
        client = self._get_client()
        start = time.perf_counter()
        sampling_kwargs = self._build_sampling_kwargs(task, sampling)
        retry_delays = (0.8, 1.6)
        last_error: Exception | None = None
        output_chunks: List[str] = []
        try:
            for attempt in range(len(retry_delays) + 1):
                output_chunks = []
                try:
                    stream = await client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=max_tokens,
                        stream=True,
                        **sampling_kwargs,
                    )
                    async for chunk in stream:
                        ch_list = getattr(chunk, "choices", None) or []
                        if not ch_list:
                            continue
                        delta_obj = getattr(ch_list[0], "delta", None)
                        delta = getattr(delta_obj, "content", None) if delta_obj is not None else None
                        if delta:
                            output_chunks.append(delta)
                            yield delta
                    log_llm_call(
                        mode=self.profile,
                        model=self.model,
                        llm_endpoint=f"{self.base_url.rstrip('/')}/chat/completions",
                        context=self._log_context_payload(context, task, sampling_kwargs),
                        duration_ms=int((time.perf_counter() - start) * 1000),
                        status="ok",
                        prompt_text=f"{system}\n{prompt}",
                        completion_text="".join(output_chunks),
                        input_payload={
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": prompt},
                            ],
                            "max_tokens": max_tokens,
                            "stream": True,
                            **sampling_kwargs,
                        },
                        output_payload={"text": "".join(output_chunks)},
                        user_id=resolve_llm_billing_user_id(getattr(self, "_user_id", None)),
                        task=task,
                        tier_override=getattr(self, "_billing_tier", None),
                        db=self._db,
                    )
                    return
                except Exception as e:
                    last_error = e
                    if attempt >= len(retry_delays) or not self._is_retryable_llm_error(e):
                        raise
                    await asyncio.sleep(retry_delays[attempt])
            if last_error is not None:
                raise last_error
        except Exception as e:
            log_llm_call(
                mode=self.profile,
                model=self.model,
                llm_endpoint=f"{self.base_url.rstrip('/')}/chat/completions",
                context=self._log_context_payload(context, task, sampling_kwargs),
                duration_ms=int((time.perf_counter() - start) * 1000),
                status="error",
                prompt_text=f"{system}\n{prompt}",
                completion_text="".join(output_chunks),
                error=str(e),
                input_payload={
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "stream": True,
                    **sampling_kwargs,
                },
                output_payload={"text": "".join(output_chunks)},
                user_id=resolve_llm_billing_user_id(getattr(self, "_user_id", None)),
                task=task,
                tier_override=getattr(self, "_billing_tier", None),
                db=self._db,
            )
            raise
