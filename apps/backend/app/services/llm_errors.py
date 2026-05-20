"""将 LLM 异常转为面向用户的简短说明（Bootstrap SSE / API 错误）。"""

from __future__ import annotations


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
    if "401" in low or "unauthorized" in low or "invalid api key" in low:
        return f"API Key 无效或未授权：{msg}"
    if "404" in low and "model" in low:
        return f"模型 id 不存在或网关未提供该模型：{msg}"
    if any(code in low for code in ("502", "503", "504", "bad gateway")):
        return f"大模型网关暂时不可用，请稍后重试：{msg}"
    return msg
