"""dabai 境界倒退判定共享纯函数。

原主链路 ``check_dabai_consistency``（绑定 Chapter/OutlineNode）已随旧写作路径退役；
此处仅保留与数据模型无关的 ``realm_regression_hit``，供实验书架 ``lab_quality``（DLB-04）复用。
"""
from __future__ import annotations

# 回忆/对比/突破自述语境标记：低境界词出现在这些语境中不算倒退
_RETRO_BEFORE = (
    "当年", "曾经", "昔日", "回忆", "回想", "那时", "当初", "彼时",
    "还是", "不过是", "区区", "突破", "晋升", "踏入", "迈入", "升入",
)
_RETRO_AFTER = ("突破", "晋升", "之后", "之时", "时期", "时候", "巅峰")


def realm_regression_hit(plain: str, term: str) -> bool:
    """低境界词是否以「现在时」出现（回忆/对比/突破自述语境豁免）。

    DBC-02 因正则误报停用是前车之鉴：阻断规则误报代价最高，
    故对「当年还是炼气期」「从炼气期突破」类提及做语境豁免，
    所有出现位置均为回忆语境时不判倒退。
    """
    if not term:
        return False
    start = 0
    while True:
        idx = plain.find(term, start)
        if idx < 0:
            return False
        before = plain[max(0, idx - 12):idx]
        after = plain[idx + len(term): idx + len(term) + 8]
        retro = (
            any(m in before for m in _RETRO_BEFORE)
            or before[-1:] in ("从", "自")
            or any(m in after for m in _RETRO_AFTER)
        )
        if not retro:
            return True
        start = idx + len(term)
