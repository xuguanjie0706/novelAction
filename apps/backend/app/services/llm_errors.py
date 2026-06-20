"""将 LLM 异常转为面向用户的简短说明（Bootstrap SSE / API 错误）。"""

from __future__ import annotations

import re


def is_response_format_rejected_error(err: BaseException) -> bool:
    """网关/模型明确拒绝 response_format 时，调用方可降级为纯 prompt JSON。"""
    status_code = getattr(err, "status_code", None)
    msg = str(err).lower()
    if isinstance(status_code, int) and status_code in (400, 422):
        if any(
            key in msg
            for key in (
                "response_format",
                "json_object",
                "json_schema",
                "structured output",
                "not supported",
                "unknown parameter",
                "invalid parameter",
                "unrecognized",
                "unsupported",
            )
        ):
            return True
    return any(
        key in msg
        for key in (
            "response_format",
            "json_object is not supported",
            "does not support response_format",
            "unsupported response_format",
        )
    )


def is_retryable_llm_error(err: BaseException) -> bool:
    """判定是否为可重试的瞬时网关/网络错误（与 AIService 内层退避一致）。"""
    if is_llm_provider_failover_error(err):
        return True
    status_code = getattr(err, "status_code", None)
    if isinstance(status_code, int) and status_code in (408, 429, 500, 502, 503, 504):
        return True
    type_name = type(err).__name__.lower()
    if any(k in type_name for k in ("connection", "timeout", "connect", "remoteprotocol")):
        return True
    msg = str(err).lower()
    return any(
        key in msg
        for key in (
            "error code: 502",
            "bad gateway",
            "timeout",
            "timed out",
            "temporarily unavailable",
            "connection error",
            "connection refused",
            "connection reset",
            "connect timeout",
            "network unreachable",
            "name or service not known",
            "ssl",
            "eof occurred",
            "peer closed",
            "incomplete chunked",
            "server disconnected",
            "without sending a response",
        )
    )


def is_llm_provider_failover_error(err: BaseException) -> bool:
    """当前线路不可用（上游失败/空响应），可切换备用 provider 重试。"""
    msg = str(err).lower()
    return any(
        key in msg
        for key in (
            "upstream error",
            "do_request_failed",
            "空 choices",
            "empty choices",
            "网关上游错误",
            "invalid token",
            "error code: 401",
            "error code: 500",
        )
    )


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
    if (
        "server disconnected" in low
        or "without sending a response" in low
        or "remoteprotocol" in type_low
    ):
        return (
            "大模型网关中途断开连接（Server disconnected）。"
            "多为网关不稳定或瞬时过载，请稍后重试该步骤，或在管理后台换一条线路。"
            f" 原始信息：{msg}"
        )
    if "upstream error" in low or "do_request_failed" in low or "网关上游错误" in msg:
        return (
            "当前大模型线路上游请求失败（网关返回空响应）。"
            "请在顶部「模型」菜单换一条线路（如默认 gemini-3.1-pro），或稍后重试。"
            f" 原始信息：{msg}"
        )
    if "空 choices" in msg or "empty choices" in low:
        return (
            "大模型网关返回了空响应（无正文）。多为所选线路不稳定或不兼容 JSON 模式。"
            "请换一条模型线路后重试。"
            f" 原始信息：{msg}"
        )
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
