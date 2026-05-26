"""
realm_attribution.py — 人物境界归因判定

判断章纲文本中的境界名是否应计作某人物的修为描写（而非「遭遇 XX 境敌人」等场景描述），
供境界成长时间轴构建使用。
"""
from __future__ import annotations

from typing import Any

from app.routers.outline.helpers.constants import PROTAGONIST_REALM_ATTRIBUTION_VERBS


def chapter_growth_scan_text(chapter: dict) -> str:
    """合并章纲中可能承载人物/境界变化的字段（人物变化 + 实力里程碑）。"""
    parts = [
        str(chapter.get("character_change") or ""),
        str(chapter.get("power_milestone") or ""),
    ]
    return " | ".join(p for p in parts if p.strip())


def character_realm_attributed(
    text: str,
    realm_name: str,
    character_names: list[str],
    *,
    max_span: int = 56,
    role_label: str | None = None,
) -> bool:
    """
    判断 text 中的 realm_name 是否应计作「该人物修为描写」。
    要求：与任一姓名/别名同处短跨度内，且出现修为归因信号。
    """
    anchors = [n for n in character_names if isinstance(n, str) and n.strip()]
    if not anchors:
        return True
    if role_label == "protagonist":
        anchors = list(dict.fromkeys([*anchors, "主角"]))
    else:
        anchors = list(dict.fromkeys(anchors))
    for pname in anchors:
        p_start = 0
        while True:
            p = text.find(pname, p_start)
            if p == -1:
                break
            r_start = 0
            while True:
                r = text.find(realm_name, r_start)
                if r == -1:
                    break
                lo = min(p, r)
                hi = max(p + len(pname), r + len(realm_name))
                if hi - lo > max_span:
                    r_start = r + 1
                    continue
                mid = text[lo:hi]
                if any(v in mid for v in PROTAGONIST_REALM_ATTRIBUTION_VERBS):
                    return True
                if f"以{realm_name}" in mid or f"从{realm_name}" in mid:
                    return True
                r_start = r + 1
            p_start = p + 1
    return False


def extract_character_realm_rank(
    chapter: dict,
    name_to_rank: dict[str, int],
    *,
    character_names: list[str] | None = None,
    role_label: str | None = None,
) -> int | None:
    """
    扫描章纲人物变化 + 实力里程碑，返回该章中计作「该人物修为」的境界最大 rank。

    当传入 character_names（非空）时，仅统计与姓名共现且带修为归因语境的境界名。
    未传或为空列表时：取文中白名单境界最大 rank。
    """
    text = chapter_growth_scan_text(chapter)
    if not text or not name_to_rank:
        return None
    use_attribution = bool(character_names)
    found_rank: int | None = None
    for realm_name, rank in name_to_rank.items():
        if not realm_name or len(realm_name) < 2 or realm_name not in text:
            continue
        if use_attribution and not character_realm_attributed(
            text, realm_name, character_names or [], role_label=role_label,
        ):
            continue
        if found_rank is None or rank > found_rank:
            found_rank = rank
    return found_rank


def parse_chapter_number_label(label: Any) -> int | None:
    """从「第15章」或纯数字章号解析整数。"""
    import re
    if label is None:
        return None
    if isinstance(label, int):
        return label if label > 0 else None
    s = str(label).strip()
    if not s:
        return None
    m = re.match(r"^\s*第\s*0*(\d+)", s)
    if m:
        return int(m.group(1))
    try:
        n = int(s)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None
