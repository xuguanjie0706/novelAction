"""
玄幻/仙侠题材：现代与科幻用语黑名单（章纲质检、正文 prompt、落库清洗共用单源）。
"""
from __future__ import annotations

from typing import Optional

# 字面命中即视为漂移（须改写为阵法、禁制、傀儡、古域、辨药、拆方等意象）。
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
    # 现代 STEM / 商业话术（易混入炼丹、势力经营描写）
    "逆向工程",
    "灵气逆向",
    "工业化",
    "流水线生产",
    "算法",
    "数据分析",
    "市场调研",
    "用户画像",
    "畅销榜",
    "市面上最畅销",
    "逻辑链",
    "优化方案",
    "临床试验",
    "科学解析",
    "化学分析",
})

# 落库前自动替换（长词优先）；质检仍可能报剩余禁词。
XUANHUAN_TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("灵气逆向工程", "以灵气拆方悟纹"),
    ("逆向工程", "拆方悟纹"),
    ("市面上最畅销", "坊市人手一份"),
    ("畅销榜", "坊市热销榜"),
    ("首席工程师", "大阵主祭"),
    ("解析并改良", "辨性重配"),
    ("科学解析", "辨药推演"),
    ("化学分析", "辨性验丹"),
    ("人工智能", "灵智禁制"),
    ("基因实验室", "血脉禁室"),
    ("星际文明", "诸天古域"),
    ("程序上传", "神识刻印"),
    ("半机械", "半傀"),
    ("机械", "机关"),
    ("控制台", "阵枢石台"),
    ("工业化", "规模化炼制"),
    ("市场调研", "坊市探价"),
    ("数据分析", "天机推演"),
    ("算法", "推演法门"),
    ("AI化", "傀儡化"),
    ("AI", "灵智"),
    ("芯片", "命纹碎片"),
    ("量子", "微尘"),
    ("星际", "诸天"),
)

OUTLINE_SANITIZE_FIELDS = (
    "title",
    "opening_hook",
    "core_event",
    "character_change",
    "foreshadow",
    "end_hook",
    "summary",
    "protagonist_want",
    "protagonist_obstacle",
    "protagonist_choice",
    "choice_cost",
    "villain_action",
    "supporting_spotlight",
    "promise_fulfilled",
)


def is_xuanhuan_like_genre(genre: Optional[str]) -> bool:
    raw = (genre or "").strip()
    return any(tag in raw for tag in ("玄幻", "仙侠", "古风", "武侠"))


def sanitize_xuanhuan_text(text: str) -> str:
    """章纲/承诺等文本落库前的现代用语替换。"""
    cleaned = text
    for src, dst in XUANHUAN_TEXT_REPLACEMENTS:
        cleaned = cleaned.replace(src, dst)
    return cleaned


def sanitize_outline_chapter(chapter: dict, genre: Optional[str]) -> dict:
    """对单章章纲 JSON 对象做玄幻用语清洗。"""
    if not is_xuanhuan_like_genre(genre):
        return chapter
    sanitized = dict(chapter)
    for field in OUTLINE_SANITIZE_FIELDS:
        value = sanitized.get(field)
        if isinstance(value, str) and value:
            sanitized[field] = sanitize_xuanhuan_text(value)
    return sanitized


def format_modern_blacklist_for_prompt(max_terms: Optional[int] = None) -> str:
    """
    拼入模型 prompt 的显式词表块；max_terms 用于极端预算限制（一般不必传）。
    """
    terms = sorted(MODERN_BLACKLIST_FOR_XUANHUAN)
    if max_terms is not None and max_terms > 0:
        terms = terms[:max_terms]
    body = "、".join(terms)
    return (
        "【现代/科幻/商业话术黑名单 — 不得出现下列词的字面写法（含对话、旁白、章纲字段）；"
        "须改为东方玄幻意象。示例：逆向工程→拆方悟纹/灵机溯源；解析丹方→辨药推演；"
        "改良丹药→重配丹纹/淬炼方脉；畅销→坊市热销】\n"
        f"{body}"
    )
