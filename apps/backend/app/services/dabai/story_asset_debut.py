"""story_assets 落库 debut 裁决 — 防第 1 章功法提前进「已拥有」台账。

设计：Bootstrap 的 plot_assets 是剧情规划，不是开局背包。
主角功法（尤其成长线）须在正文/复盘获得后再入账，否则写第 1 章时
导演单会与章纲「认主获宝」叙事冲突。
"""
from __future__ import annotations

_GROWTH_ROLES = frozenset({"成长线"})


def resolve_plot_asset_debut(asset: dict, protag: str) -> str:
    """判定 plot_asset 应落库为 start（开局已有）还是 later（线索规划）。

    Args:
        asset: story_assets.plot_assets 单项。
        protag: 主角人名。

    Returns:
        ``"start"`` 或 ``"later"``。
    """
    raw = str(asset.get("debut") or "start").strip().lower()
    kind = str(asset.get("kind") or "item").strip().lower()
    role = str(asset.get("plot_role") or "").strip()
    owner = str(asset.get("owner") or protag).strip() or protag

    if role in _GROWTH_ROLES:
        return "later"
    # 主角功法默认走剧情获得（金手指单独建账，不在 plot_assets）
    if kind == "skill" and owner == protag:
        return "later"
    if raw == "later":
        return "later"
    return "start"


def plot_role_from_description(description: str) -> str:
    """从 ``[成长线] …`` 描述里提取 plot_role。"""
    text = (description or "").strip()
    if text.startswith("[") and "]" in text:
        return text[1:text.index("]")].strip()
    return ""
