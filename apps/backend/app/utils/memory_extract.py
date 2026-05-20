"""记忆提取落库字段清洗（AI JSON → MemoryChunk 安全 kwargs）。"""
from __future__ import annotations

from typing import Any, Dict, List

_ALLOWED_MEMORY_TYPES = frozenset(
    {"event", "character_state", "foreshadow", "setting", "conflict"}
)


def _clamp_importance_score(raw: Any) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, value))


def sanitize_extracted_memory_item(item: Any) -> Dict[str, Any] | None:
    """
    将 AI 返回的单条记忆 dict 转为 MemoryChunk 可接受的字段。

    - 忽略未知键，避免 ``MemoryChunk(**item)`` 因多余字段抛 TypeError
    - ``content`` 为空时返回 None（调用方跳过）
    - ``importance_score`` 钳制到 [0.0, 1.0]
    """
    if not isinstance(item, dict):
        return None

    content = (item.get("content") or "").strip()
    if not content:
        return None

    memory_type = str(item.get("memory_type") or "event").strip()
    if memory_type not in _ALLOWED_MEMORY_TYPES:
        memory_type = "event"

    title = item.get("title")
    if title is not None:
        title = str(title).strip()[:200] or None

    raw_tags = item.get("tags")
    tags: List[str] = []
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()][:8]

    return {
        "memory_type": memory_type,
        "title": title,
        "content": content,
        "tags": tags,
        "importance_score": _clamp_importance_score(item.get("importance_score")),
    }
