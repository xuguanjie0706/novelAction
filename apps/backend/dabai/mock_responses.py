"""【已废弃】离线 mock 数据已移除。

历史背景：本模块曾内置一份硬编码的「废柴林凡觉醒吞噬系统」样本，供 ``--mock``
离线跑通 bootstrap。该样本导致所有 mock 项目产出雷同内容（第一章尤甚），已整体下线。

现在 dabai 链路只走真实 LLM（见 ``dabai/llm_client.py``）。保留此存根仅为兼容可能的
旧 import；任何调用都会显式报错，提醒改用真实模式。
"""

from __future__ import annotations

from typing import Any

_REMOVED_MSG = (
    "dabai 离线 mock 数据已移除：请配置 DABAI_BASE_URL / DABAI_API_KEY / DABAI_MODEL "
    "走真实 LLM。"
)


def get(step: str, cfg: Any, meta: dict | None = None) -> Any:  # noqa: ARG001
    """旧接口存根：mock 数据已删除，调用即报错。"""
    raise RuntimeError(_REMOVED_MSG)
