"""
各创作场景的 max_tokens（OpenAI 兼容 chat.completions）。

Gemini 等长上下文模型：数值在 app.config.Settings 中可用环境变量覆盖。
本地短上下文模型：保持保守默认，避免撑爆 8k context。
"""
from app.config import settings


def _is_gemini(profile: str) -> bool:
    return profile == "gemini"


def max_tokens_expand_outline(profile: str) -> int:
    return (
        settings.GEMINI_EXPAND_OUTLINE_MAX_TOKENS
        if _is_gemini(profile)
        else settings.LOCAL_EXPAND_OUTLINE_MAX_TOKENS
    )


def max_tokens_outline_quality_check(profile: str) -> int:
    return (
        settings.GEMINI_OUTLINE_QUALITY_MAX_TOKENS
        if _is_gemini(profile)
        else settings.LOCAL_OUTLINE_QUALITY_MAX_TOKENS
    )


def max_tokens_chapter_quality_check(large_context: bool) -> int:
    return (
        settings.GEMINI_CHAPTER_QUALITY_MAX_TOKENS
        if large_context
        else settings.LOCAL_CHAPTER_QUALITY_MAX_TOKENS
    )


def max_tokens_coherence_check(large_context: bool) -> int:
    return (
        settings.GEMINI_COHERENCE_CHECK_MAX_TOKENS
        if large_context
        else settings.LOCAL_COHERENCE_CHECK_MAX_TOKENS
    )


def max_tokens_draft_stream(large_context: bool) -> int:
    return (
        settings.GEMINI_DRAFT_STREAM_MAX_TOKENS
        if large_context
        else settings.LOCAL_DRAFT_STREAM_MAX_TOKENS
    )


def max_tokens_auto_debrief() -> int:
    return settings.AUTO_DEBRIEF_MAX_TOKENS


def max_tokens_plan_full_structure(profile: str) -> int:
    return (
        settings.GEMINI_PLAN_STRUCTURE_MAX_TOKENS
        if _is_gemini(profile)
        else settings.LOCAL_PLAN_STRUCTURE_MAX_TOKENS
    )


def max_tokens_suggest_stream(profile: str) -> int:
    return (
        settings.GEMINI_SUGGEST_STREAM_MAX_TOKENS
        if _is_gemini(profile)
        else settings.LOCAL_SUGGEST_STREAM_MAX_TOKENS
    )


def max_tokens_extract_memory(profile: str) -> int:
    return (
        settings.GEMINI_EXTRACT_MEMORY_MAX_TOKENS
        if _is_gemini(profile)
        else settings.LOCAL_EXTRACT_MEMORY_MAX_TOKENS
    )
