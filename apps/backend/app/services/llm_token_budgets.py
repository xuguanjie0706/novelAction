"""
各创作场景的 max_tokens（OpenAI 兼容 chat.completions）。

统一使用远程大上下文模型（Gemini 等）；数值在 app.config.Settings 中可用环境变量覆盖。
所有返回值不低于 ``Settings.LLM_COMPLETION_MIN_TOKENS``（默认 10000）。
"""
from app.config import settings


def min_completion_tokens() -> int:
    """全局 completion 下限，供各调用方直接引用。"""
    return int(settings.LLM_COMPLETION_MIN_TOKENS)


def ensure_min_completion_tokens(max_tokens: int) -> int:
    """将任意 max_tokens 抬升到全局下限之上。"""
    return max(int(max_tokens), min_completion_tokens())


def _budget(value: int) -> int:
    return ensure_min_completion_tokens(value)


def max_tokens_expand_outline(_profile: str = "gemini") -> int:
    return _budget(settings.GEMINI_EXPAND_OUTLINE_MAX_TOKENS)


def max_tokens_outline_quality_check(_profile: str = "gemini") -> int:
    return _budget(settings.GEMINI_OUTLINE_QUALITY_MAX_TOKENS)


def max_tokens_chapter_quality_check(_large_context: bool = True) -> int:
    return _budget(settings.GEMINI_CHAPTER_QUALITY_MAX_TOKENS)


def max_tokens_quality_micro_patch(_large_context: bool = True) -> int:
    """质量债务局部替换：输出较短 JSON + 替换段。"""
    return min_completion_tokens()


def max_tokens_coherence_check(_large_context: bool = True) -> int:
    return _budget(settings.GEMINI_COHERENCE_CHECK_MAX_TOKENS)


def max_tokens_coherence_apply(_large_context: bool = True) -> int:
    return _budget(settings.GEMINI_COHERENCE_APPLY_MAX_TOKENS)


def max_tokens_draft_stream(_large_context: bool = True) -> int:
    return _budget(settings.GEMINI_DRAFT_STREAM_MAX_TOKENS)


def max_tokens_auto_debrief(_profile: str = "default") -> int:
    """复盘 JSON 输出复杂，需足够 completion 预算。"""
    return _budget(settings.GEMINI_AUTO_DEBRIEF_MAX_TOKENS)


def max_tokens_pre_write_warning(_profile: str = "gemini") -> int:
    """写前预警主编审稿 JSON；thinking 模型需预留推理 + 可见 JSON 双份预算。"""
    return _budget(int(settings.GEMINI_PRE_WRITE_WARNING_MAX_TOKENS))


def max_tokens_plan_full_structure(_profile: str = "gemini") -> int:
    return _budget(settings.GEMINI_PLAN_STRUCTURE_MAX_TOKENS)


def max_tokens_suggest_stream(_profile: str = "gemini") -> int:
    return _budget(settings.GEMINI_SUGGEST_STREAM_MAX_TOKENS)


def max_tokens_extract_memory(_profile: str = "gemini") -> int:
    return _budget(settings.GEMINI_EXTRACT_MEMORY_MAX_TOKENS)


def max_tokens_bootstrap_completion() -> int:
    """Bootstrap 串行各步大块 JSON 的 ``max_tokens``，读 ``Settings.BOOTSTRAP_COMPLETION_MAX_TOKENS``。"""
    return _budget(int(settings.BOOTSTRAP_COMPLETION_MAX_TOKENS))


def max_tokens_scene_draft(_large_context: bool = True) -> int:
    """逐场起草的 ``max_tokens``。"""
    return min_completion_tokens()


def max_tokens_vol_expand_chapters() -> int:
    """按卷懒展开章纲的单批 ``max_tokens``。

    30章×15字段的完整 JSON 输出约需 8000-16000 token；
    60章拆两批，每批同量。默认 32768，可在 .env 中用
    ``VOL_EXPAND_CHAPTERS_MAX_TOKENS`` 覆盖（如 65536）。
    """
    return _budget(int(settings.VOL_EXPAND_CHAPTERS_MAX_TOKENS))


def max_tokens_vol1_chapter_plans() -> int:
    """Bootstrap Step 12.5 第一卷章级大纲的单次 ``max_tokens``。

    实测 30 章丰富 JSON ≈ 16k completion tokens；60 章整卷一次生成建议 ≥32k。
    默认 40960（适配 Gemini / 远程大上下文）；``.env`` 用 ``VOL1_CHAPTERS_MAX_TOKENS`` 覆盖。
    """
    return _budget(int(settings.VOL1_CHAPTERS_MAX_TOKENS))
