"""
玄幻/仙侠题材：现代与科幻用语黑名单（章纲质检、正文 prompt 共用单源）。
"""
from __future__ import annotations

from typing import Optional

# 字面命中即视为漂移（须改写为阵法、禁制、傀儡、古域等意象）。
MODERN_BLACKLIST_FOR_XUANHUAN: frozenset[str] = frozenset({
    "AI",
    "人工智能",
    "首席工程师",
    "半机械人",
    "机械改造",
    "芯片",
    "量子",
    "基因实验室",
    "克隆体",
    "电脑",
    "服务器",
    "处理器",
    "代码块",
    "控制台",
    "程序上传",
    "宇宙飞船",
    "飞船",
    "星舰",
    "战舰",
    "星际文明",
    "机甲",
    "机器人",
    "激光炮",
    "等离子",
    "纳米机器人",
    # 常见「赛博修仙」漂移词（传统玄幻应回避）
    "赛博",
    "赛博朋克",
    "备份体",
    "原型机",
    "数字生命",
    "元宇宙",
    "虚拟现实",
    "区块链",
})


def is_xuanhuan_like_genre(genre: Optional[str]) -> bool:
    raw = (genre or "").strip()
    return any(tag in raw for tag in ("玄幻", "仙侠", "古风", "武侠"))


def format_modern_blacklist_for_prompt(max_terms: Optional[int] = None) -> str:
    """
    拼入模型 prompt 的显式词表块；max_terms 用于极端预算限制（一般不必传）。
    """
    terms = sorted(MODERN_BLACKLIST_FOR_XUANHUAN)
    if max_terms is not None and max_terms > 0:
        terms = terms[:max_terms]
    body = "、".join(terms)
    return (
        "【现代/科幻用语黑名单 — 不得出现下列词的字面写法（含对话与旁白）；"
        "须改为东方玄幻意象，如阵法中枢、古禁制、神纹、天机枢纽、傀儡机关、血脉禁室等】\n"
        f"{body}"
    )
