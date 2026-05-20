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


def max_tokens_quality_micro_patch(large_context: bool) -> int:
    """质量债务局部替换：输出较短 JSON + 替换段。"""
    return 4096 if large_context else 2200


def max_tokens_coherence_check(large_context: bool) -> int:
    return (
        settings.GEMINI_COHERENCE_CHECK_MAX_TOKENS
        if large_context
        else settings.LOCAL_COHERENCE_CHECK_MAX_TOKENS
    )


def max_tokens_coherence_apply(large_context: bool) -> int:
    return (
        settings.GEMINI_COHERENCE_APPLY_MAX_TOKENS
        if large_context
        else settings.LOCAL_COHERENCE_APPLY_MAX_TOKENS
    )


def max_tokens_draft_stream(large_context: bool) -> int:
    return (
        settings.GEMINI_DRAFT_STREAM_MAX_TOKENS
        if large_context
        else settings.LOCAL_DRAFT_STREAM_MAX_TOKENS
    )


def max_tokens_auto_debrief(profile: str = "default") -> int:
    """复盘 JSON 输出复杂，需按模型分档，不能统一用小值。"""
    return (
        settings.GEMINI_AUTO_DEBRIEF_MAX_TOKENS
        if _is_gemini(profile)
        else settings.LOCAL_AUTO_DEBRIEF_MAX_TOKENS
    )


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


def max_tokens_bootstrap_completion() -> int:
    """Bootstrap 串行各步大块 JSON 的 ``max_tokens``，读 ``Settings.BOOTSTRAP_COMPLETION_MAX_TOKENS``。"""
    return int(settings.BOOTSTRAP_COMPLETION_MAX_TOKENS)


def max_tokens_scene_draft(large_context: bool) -> int:
    """逐场起草的 ``max_tokens``：单场字数约 300-800，本地给 1200，Gemini 给 3000。"""
    return 3000 if large_context else 1200


def max_tokens_vol_expand_chapters() -> int:
    """按卷懒展开章纲的单批 ``max_tokens``。

    30章×15字段的完整 JSON 输出约需 8000-16000 token；
    60章拆两批，每批同量。默认 32768，可在 .env 中用
    ``VOL_EXPAND_CHAPTERS_MAX_TOKENS`` 覆盖（如 65536）。
    """
    return int(settings.VOL_EXPAND_CHAPTERS_MAX_TOKENS)


def max_tokens_vol1_chapter_plans() -> int:
    """Bootstrap Step 12.5 第一卷章级大纲的单次 ``max_tokens``。

    实测 30 章丰富 JSON ≈ 16k completion tokens；60 章整卷一次生成建议 ≥32k。
    默认 40960（适配 Gemini / 远程大上下文）；``.env`` 用 ``VOL1_CHAPTERS_MAX_TOKENS`` 覆盖。
    """
    return int(settings.VOL1_CHAPTERS_MAX_TOKENS)
