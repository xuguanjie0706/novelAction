"""dabai 位置台账坐标（A 档）：「地图区域·具体地点」仅作系统对齐，非正文措辞。

正文须自然地名；本模块只服务章纲/导演单/面板快照/人物页台账。
"""
from __future__ import annotations

LEDGER_SEP = "·"
_MAX_LOC_LEN = 50


def split_ledger_location(location: str) -> tuple[str, str]:
    """拆分为 (地图区域, 具体地点)；无分隔符时 place=全文、map 为空。"""
    text = (location or "").strip()
    if not text:
        return "", ""
    if LEDGER_SEP in text:
        region, _, place = text.partition(LEDGER_SEP)
        return region.strip(), place.strip()
    return "", text


def location_region_key(location: str) -> str:
    """粗粒度区域键（与 lab_prompt_shared.location_key 一致）。"""
    region, _ = split_ledger_location(location)
    base = region or (location or "").strip()
    return base[:6]


def locations_equivalent(a: str, b: str) -> bool:
    """两坐标是否指同一叙事现场（容忍细地点改写、同区域换说法）。"""
    left = (a or "").strip()
    right = (b or "").strip()
    if not left or not right:
        return left == right
    if left == right:
        return True
    lk, rk = location_region_key(left), location_region_key(right)
    if lk and rk and lk == rk:
        return True
    if left in right or right in left:
        return True
    return False


def normalize_ledger_location(
    raw: str,
    *,
    prev_location: str = "",
    outline_location: str = "",
) -> str:
    """归一化台账坐标：补全「地图·地点」、截断长度。

    Args:
        raw: 复盘/导演单给出的位置。
        prev_location: 上章面板快照 location（优先继承区域前缀）。
        outline_location: 本章章纲 location（次选区域来源）。
    """
    text = (raw or "").strip()
    if not text:
        return ""
    if LEDGER_SEP in text:
        return text[:_MAX_LOC_LEN]

    for anchor in (prev_location, outline_location):
        region, _ = split_ledger_location(anchor)
        if not region and anchor.strip():
            region = anchor.strip().split(LEDGER_SEP)[0].strip()
        if region and region not in text:
            return f"{region}{LEDGER_SEP}{text}"[:_MAX_LOC_LEN]
    return text[:_MAX_LOC_LEN]


def default_location_change_reason(
    new_loc: str,
    prev_loc: str,
    explicit: str = "",
) -> str:
    """位置未变时的台账默认依据文案。"""
    if explicit.strip():
        return explicit.strip()[:500]
    if locations_equivalent(new_loc, prev_loc):
        return "本章未离开当前区域"
    return ""

def prose_has_ledger_location_dot(text: str) -> bool:
    """正文是否出现「汉字·汉字」式台账坐标拼接（A 档质检 warning 用）。"""
    import re
    plain = re.sub(r"<[^>]+>", "", text or "")
    return bool(re.search(r"[\u4e00-\u9fff]{2,10}·[\u4e00-\u9fff]{2,16}", plain))
