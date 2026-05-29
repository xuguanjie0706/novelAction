"""将 LLM 异常转为面向用户的简短说明（Bootstrap SSE / API 错误）。"""

from __future__ import annotations

import re


def format_llm_error_message(exc: BaseException) -> str:
    """把 OpenAI SDK / httpx 异常转成可操作的提示，保留原始信息便于排查。"""
    msg = str(exc).strip() or type(exc).__name__
    low = msg.lower()
    type_low = type(exc).__name__.lower()

    if "connection" in type_low or low in ("connection error.", "connection error"):
        return (
            "无法连接大模型网关（Connection error）。请检查："
            "① 管理后台「大模型」线路是否启用；"
            "② base_url 与 API Key 是否正确；"
            "③ 本机网络能否访问该地址（管理后台可点「测试连接」）。"
            f" 原始信息：{msg}"
        )
    if "timeout" in low or "timed out" in low:
        return (
            f"大模型请求超时：{msg}。"
            "可稍后重试，或在 .env 调大 LLM_HTTP_READ_TIMEOUT。"
        )
    if "blocked" in low or "permissiondenied" in type_low:
        return (
            "模型请求被服务商安全策略拦截（Your request was blocked）。"
            "可尝试：① 减少选中章节数或缩短正文；② 换一条大模型线路；③ 检查正文是否含敏感表述。"
            f" 原始信息：{msg}"
        )
    if "401" in low or "unauthorized" in low or "invalid api key" in low:
        return f"API Key 无效或未授权：{msg}"
    if "404" in low and "model" in low:
        return f"模型 id 不存在或网关未提供该模型：{msg}"
    if "bad gateway" in low or re.search(r"\b(502|503|504)\b", low):
        return f"大模型网关暂时不可用，请稍后重试：{msg}"
    if "peer closed" in low or "incomplete chunked" in low:
        return (
            "大模型在流式输出时断开了连接（常见于上下文过长或网关不稳定）。"
            "建议：① 减少「参考章节」勾选数量（先试 2～3 章）；"
            "② 稍后重试；③ 换一条大模型线路。"
            f" 原始信息：{msg}"
        )
    return msg
