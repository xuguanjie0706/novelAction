"""OpenAI 兼容 LLM 客户端。

设计目标：
  - 标准 OpenAI /chat/completions（任何兼容服务，base_url 可换）。
  - JSON 解析容错：剥离 ```json 围栏、截取首个 {...} 或 [...]。
依赖：`openai` 包。
"""

from __future__ import annotations

import json
import re
from typing import Any

from dabai.config import DabaiConfig


class LLMError(RuntimeError):
    """LLM 调用 / 解析失败。"""


def parse_json(raw: Any) -> Any:
    """模块级 JSON 解析（剥 ```围栏 + 截取数组/对象）。供 AIService 桥接复用。"""
    return DabaiLLM._parse_json(raw)


class DabaiLLM:
    """轻量 LLM 封装。一个实例对应一次 bootstrap 运行。"""

    def __init__(self, config: DabaiConfig):
        self.config = config
        self._client = self._build_client()

    def _build_client(self):
        if not self.config.base_url:
            raise LLMError(
                "缺少 base_url：经 API 调用时由所选模型/线路解析；"
                "命令行直跑请设 DABAI_BASE_URL。"
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMError("缺少 openai 包：pip install openai") from exc
        return OpenAI(
            base_url=self.config.base_url,
            api_key=(self.config.api_key or "not-required"),
        )

    # ── 对外主接口 ────────────────────────────────────────────────────────────
    def generate_json(
        self, step: str, system: str, user: str, meta: dict | None = None,
    ) -> Any:
        """调用 LLM 并返回解析后的 JSON（dict 或 list）。

        meta: 步骤级附加信息（如章纲分批的 batch_start/batch_end）。
        """
        raw = self._call_real(step, system, user)
        return self._parse_json(raw)

    def _call_real(self, step: str, system: str, user: str) -> str:
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature_for(step),
            "max_tokens": self.config.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            try:
                resp = self._client.chat.completions.create(
                    **payload,
                    response_format={"type": "json_object"},
                )
            except Exception as exc:
                from app.services.llm_errors import is_response_format_rejected_error
                if not is_response_format_rejected_error(exc):
                    raise
                resp = self._client.chat.completions.create(**payload)
            return resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"{step} LLM 调用失败：{exc}") from exc

    # ── JSON 解析（剥围栏 + 截取数组/对象）──────────────────────────────────────
    @staticmethod
    def _parse_json(raw: str) -> Any:
        if isinstance(raw, (dict, list)):
            return raw
        text = (raw or "").strip()
        # 去掉 ```json ... ``` 围栏
        fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 容错：截取首个完整 [...] 或 {...}
        for opener, closer in (("[", "]"), ("{", "}")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue
        raise LLMError(f"无法解析 JSON，原文尾部：{text[-300:]!r}")
