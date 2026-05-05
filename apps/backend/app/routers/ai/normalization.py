import re
from typing import Optional

from app.routers.ai.constants import _ALLOWED_CHARACTER_STATUS, _ALLOWED_STORYLINE_STATUS


def normalize_character_status(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    text = raw.strip().lower()
    if not text:
        return None
    token = re.split(r"[\s（(，,;；。!！]", text, maxsplit=1)[0]
    alias = {
        "normal": "alive",
        "living": "alive",
        "active": "alive",
        "deaded": "dead",
        "deceased": "dead",
    }
    candidate = alias.get(token, token)
    if candidate in _ALLOWED_CHARACTER_STATUS:
        return candidate
    if "dead" in text or "死亡" in text:
        return "dead"
    if "missing" in text or "失踪" in text:
        return "missing"
    if "sealed" in text or "封印" in text:
        return "sealed"
    if "transform" in text or "变身" in text or "异化" in text:
        return "transformed"
    if "alive" in text or "存活" in text or "生还" in text or "活着" in text:
        return "alive"
    return None


def normalize_storyline_status(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    token = re.split(r"[\s（(，,;；。!！]", raw.strip().lower(), maxsplit=1)[0]
    if token in _ALLOWED_STORYLINE_STATUS:
        return token
    return None
