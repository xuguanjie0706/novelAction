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


def extract_upstream_error(response: Any) -> str | None:
    """OpenAI 兼容网关偶发 HTTP 200 但 body 内嵌 error、choices 为空。"""
    if response is None:
        return None
    err = getattr(response, "error", None)
    if err is None and hasattr(response, "model_dump"):
        try:
            err = response.model_dump().get("error")
        except Exception:
            err = None
    if not err:
        return None
    if isinstance(err, dict):
        parts = [err.get("message"), err.get("code"), err.get("type")]
        text = " — ".join(str(p).strip() for p in parts if p)
        return text or str(err)
    return str(err).strip() or None


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
