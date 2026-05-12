"""Bootstrap SSE 事件序列化。

`sse(event, **kwargs)` 把 step_start / step_done / error / complete 等事件 payload
打包成 `data: {...}\\n\\n` 行，统一由薄壳层 yield。

向后兼容：旧 `services/generation_service.py` 顶部以 `_sse` 别名重新导出。
"""

from __future__ import annotations

import json


def sse(event: str, **kwargs) -> str:
    """构造 SSE 行：`data: {"event": ..., **payload}\\n\\n`"""
    payload = {"event": event, **kwargs}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
