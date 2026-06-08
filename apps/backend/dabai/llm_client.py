"""OpenAI 兼容 LLM 客户端 + 离线 mock 分发。

设计目标：
  - 真实模式：标准 OpenAI /chat/completions（任何兼容服务，base_url 可换）。
  - mock 模式：不发网络请求，从 mock_responses 取该步预置 JSON，链路照常跑通。
  - JSON 解析容错：剥离 ```json 围栏、截取首个 {...} 或 [...]。
依赖：真实模式需要 `openai` 包；mock 模式零依赖。
"""

from __future__ import annotations

import json
import re
from typing import Any

from dabai.config import DabaiConfig
from dabai import mock_responses


class LLMError(RuntimeError):
    """LLM 调用 / 解析失败。"""


def parse_json(raw: Any) -> Any:
    """模块级 JSON 解析（剥 ```围栏 + 截取数组/对象）。供 AIService 桥接复用。"""
    return DabaiLLM._parse_json(raw)


class DabaiLLM:
    """轻量 LLM 封装。一个实例对应一次 bootstrap 运行。"""

    def __init__(self, config: DabaiConfig):
        self.config = config
        self._client = None
        if not config.mock:
            self._client = self._build_client()

    def _build_client(self):
        if not self.config.base_url:
            raise LLMError(
                "真实模式缺少 base_url：经 API 调用时由所选模型/线路解析；"
                "命令行直跑请设 DABAI_BASE_URL，或用 --mock 离线跑通。"
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
        """调用 LLM（或 mock）并返回解析后的 JSON（dict 或 list）。

        meta: 步骤级附加信息（如章纲分批的 batch_start/batch_end），mock 据此切片。
        """
        if self.config.mock:
            raw = mock_responses.get(step, self.config, meta or {})
        else:
            raw = self._call_real(step, system, user)
        return self._parse_json(raw)

    def _call_real(self, step: str, system: str, user: str) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self.config.model,
                temperature=self.config.temperature_for(step),
                max_tokens=self.config.max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
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
