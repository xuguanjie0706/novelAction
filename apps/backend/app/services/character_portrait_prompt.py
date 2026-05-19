"""根据人物结构化字段拼装图片模型 prompt。"""
from __future__ import annotations

from app.models import Character

_ROLE_EN = {
    "protagonist": "protagonist hero",
    "antagonist": "main antagonist villain",
    "supporting": "important supporting character",
    "neutral": "neutral side character",
}


def build_character_sprite_prompt(char: Character, *, style_hint: str = "") -> str:
    """生成横排 4 帧人物雪碧图的英文 prompt（多数图片模型对英文更稳）。"""
    parts: list[str] = [
        "Chinese xianxia fantasy novel character sprite sheet,",
        f'character name "{char.name}",',
        _ROLE_EN.get(char.role or "supporting", "character") + ",",
    ]
    if char.gender:
        parts.append(f"gender: {char.gender},")
    if char.age:
        parts.append(f"age: {char.age},")
    if char.appearance:
        parts.append(f"appearance: {char.appearance[:400]},")
    if char.clothing_style:
        parts.append(f"clothing: {char.clothing_style[:200]},")
    elif char.faction:
        parts.append(f"faction attire from {char.faction[:80]},")
    if char.personality:
        parts.append(f"personality expression: {char.personality[:150]},")
    if char.current_realm:
        parts.append(f"cultivation realm vibe: {char.current_realm[:80]},")
    traits = char.special_traits or []
    if traits:
        parts.append("special traits: " + ", ".join(str(t) for t in traits[:5]) + ",")

    parts.append(
        "layout: exactly 4 full-body poses in one horizontal row on plain soft gradient background, "
        "poses: front standing, three-quarter view, dynamic action, calm portrait close stance, "
        "consistent face and outfit across all frames, clean game RPG sprite sheet, "
        "high detail illustration, no text, no watermark, no multiple characters."
    )
    if style_hint.strip():
        parts.append(style_hint.strip())
    return " ".join(parts)
