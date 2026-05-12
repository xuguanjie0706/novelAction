"""题材护栏：genre_kit + 玄幻现代词黑名单（与 legacy ``ai_service`` 模块级函数一致）。"""

from app.services.genre_kit import get_genre_guardrail
from app.services.xuanhuan_lexicon import (
    format_modern_blacklist_for_prompt,
    is_xuanhuan_like_genre,
)


def genre_guardrail_text(raw_genre: str) -> str:
    """
    章纲扩写与正文起草共用：按作品类型注入完整 genre_kit。
    玄幻/仙侠额外追加现代词黑名单。
    """
    kit_text = get_genre_guardrail(raw_genre)
    genre_text = (raw_genre or "").strip()
    if is_xuanhuan_like_genre(genre_text):
        modern = format_modern_blacklist_for_prompt()
        return f"{kit_text}\n\n【现代/科幻用语黑名单（玄幻/仙侠专用）】\n{modern}"
    return kit_text
