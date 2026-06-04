"""从 LLM chat completion message 提取可见正文（兼容 thinking / reasoning 字段）。"""
from __future__ import annotations

import re
from typing import Any


def _strip_think_wrappers(text: str) -> str:
    """去掉常见思考标签包裹，保留标签外正文。"""
    return re.sub(
        r"<think>[\s\S]*?</think>",
        "",
        (text or "").strip(),
        flags=re.DOTALL,
    ).strip()


def _salvage_json_from_think_blocks(text: str) -> str:
    """thinking 模型偶发把 JSON 全写在思考标签内，标签外为空。"""
    match = re.search(
        r"<think>([\s\S]+?)</think>",
        text or "",
        flags=re.DOTALL,
    )
    if not match:
        return ""
    inner = match.group(1).strip()
    if "{" in inner or "[" in inner:
        return inner
    return ""


def extract_llm_response_text(raw: str | None) -> str:
    """提取可解析的正文：先去思考标签；若为空则尝试从标签内 salvage JSON。"""
    text = (raw or "").strip()
    if not text:
        return ""
    visible = _strip_think_wrappers(text)
    if visible:
        return visible
    return _salvage_json_from_think_blocks(text)


def message_completion_text(message: Any) -> str:
    """从 OpenAI 兼容 message 对象读取正文（content / reasoning_content 等）。"""
    if message is None:
        return ""
    parts: list[str] = []
    for attr in ("content", "reasoning_content", "reasoning"):
        val = getattr(message, attr, None)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
    if not parts and hasattr(message, "model_dump"):
        try:
            data = message.model_dump()
            for key in ("content", "reasoning_content", "reasoning"):
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    parts.append(val.strip())
        except Exception:
            pass
    combined = "\n".join(parts).strip()
    return extract_llm_response_text(combined)
