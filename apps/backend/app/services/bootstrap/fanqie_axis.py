"""番茄 Bootstrap 境界轴判定（社会阶梯 vs 修仙主轴）。

仅依据 Step0 ``fanqie_positioning.genre_archetype``（算法立项锁定的类型公式），
不接受 ``cultivation_axis`` / ``fanqie_axis_kind`` 等 extra 手动覆写。
"""
from __future__ import annotations

# 与 algo_positioning._FANQIE_ARCHETYPES 中唯一的修仙公式对齐
XIANXIA_GENRE_ARCHETYPE = "修仙打脸流"

_XIANXIA_ARCHETYPE_KEYWORDS = ("修仙", "仙侠", "修真")


def is_xianxia_archetype(ctx: dict) -> bool:
    """是否走修仙境界主轴（cultivation_ladder）。

    Args:
        ctx: Bootstrap ctx；须含 Step0 写入的 ``fanqie_positioning``。

    Returns:
        True 当且仅当类型公式为官方「修仙打脸流」或含修仙/仙侠/修真关键词。
    """
    pos = ctx.get("fanqie_positioning")
    if not isinstance(pos, dict):
        return False
    archetype = str(pos.get("genre_archetype") or "").strip()
    if not archetype:
        return False
    if archetype == XIANXIA_GENRE_ARCHETYPE:
        return True
    return any(k in archetype for k in _XIANXIA_ARCHETYPE_KEYWORDS)
