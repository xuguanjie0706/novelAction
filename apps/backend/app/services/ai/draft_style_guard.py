"""
写章风格守门：反「AI 腔」套话去重 + 章级情绪预算预警（零额外 LLM）。

设计动机（番茄纯爽文）：
1. AI 网文最大的「一眼假」不是穿帮，是跨章累积的同质化句式——「嘴角勾起一抹弧度」
   「一股暖流涌上心头」「心中一凛」之类套话反复出现。``draft.chapter`` 的
   frequency/presence_penalty 只能压**单章内**重复，压不住跨章口头禅。
2. 番茄读者耐心极低，连续多章「憋屈/虐」会批量弃书；卷级 ``emotion_arc`` 拦不住
   章级的局部憋屈过载。

本模块**不调用 LLM**：套话清单来自对「近 N 章已写正文」的正则计数（数据驱动，
只禁真正高频出现的），情绪预算来自 ``OutlineNode.emotional_tone`` 的连续基调统计。

落点：由 ``draft_continuity_bridge.build_draft_continuity_bridge_block`` 末尾聚合
``build_draft_style_guard_block``，经 ``draft_ctx_bridge.resolve_draft_bridge_context``
→ ``assemble_full`` 的 ``draft_bridge_context`` 注入 draft prompt（见 ``draft_stream.py``）。

设计与 ``draft_continuity_bridge`` 同构（台账/既有数据 → 写章期硬约束）。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 仅类型检查期引入，运行期延迟导入，便于纯逻辑函数独立单测
    from sqlalchemy.orm import Session

    from app.models import Chapter, OutlineNode

# 扫描窗口：取当前章之前最近的 N 章已写正文。
_RECENT_CHAPTER_WINDOW = 6
# 单章正文低于此字数视为空/占位，跳过。
_MIN_CHAPTER_CHARS = 200

# 反 AI 腔套话库：(展示名, 正则)。只有真正高频命中的才会被列入禁用清单，
# 因此宁可多列候选；不命中不会污染 prompt。
_CLICHE_PATTERNS: list[tuple[str, str]] = [
    ("嘴角勾起 / 一抹弧度", r"嘴角(微微|轻轻)?(勾起|扬起|上扬)|勾起一抹|一抹(弧度|笑意|冷笑|弧线|苦笑)"),
    ("不知为何 / 莫名", r"不知为何|不知怎的|不知为什么|莫名(其妙|的|地)"),
    ("暖流/寒意涌上心头", r"一股(暖流|寒意|暖意|热流|凉意).{0,6}(涌上|涌起|袭来)|涌上心头|涌上心间"),
    ("心中一凛 / 心头一震", r"心(中|头|里)一(凛|震|颤|动|沉|紧|寒|惊)"),
    ("深吸一口气", r"深(深)?(地|的)?吸(了)?(一)?口气"),
    ("眼中闪过一丝", r"(眼中|眼底|目光中|眼神中|眸子里)闪过一(丝|抹)"),
    ("不由得 / 不禁 / 情不自禁", r"不由得|不由自主|情不自禁|不禁"),
    ("仿佛 / 似乎（滥用）", r"仿佛|彷佛|似乎|好似|宛如|犹如"),
    ("空气凝固 / 死一般寂静", r"空气(仿佛|似乎|瞬间)?(凝固|凝结)|死(一般|一样)(的)?(寂静|沉默)|落针可闻"),
    ("时间仿佛静止", r"(时间|世界)(仿佛|似乎)?(静止|凝固|停止)|仿佛过了(一个)?(世纪|许久|很久)"),
    ("瞳孔骤缩", r"瞳孔(骤|猛|微)?(缩|然一缩|然收缩)|瞳孔一(震|缩)"),
    ("脸色骤变 / 大变", r"脸色(骤变|大变|微变|一变|铁青|煞白)"),
    ("冷哼一声", r"冷哼(了)?一声|冷笑(一声|一下)|嗤笑一声"),
]

# 句子切分（用于句首词频统计）。
_SENT_SPLIT = re.compile(r"[。！？!?\n]+")
# 句首若以标点/引号/破折号开头则跳过（不是真正的叙述句首）。
_HEAD_SKIP = re.compile(r"^[\s\"'“”‘’（()「」『』\-—…·、，,.]")

# 视为「憋屈/压抑」基调的关键词（命中即计入连续憋屈）。
_DEPRESSIVE_TONE_KEYS = (
    "憋屈", "压抑", "虐", "沉重", "悲", "绝望", "屈辱", "隐忍",
    "至暗", "低落", "压制", "灰暗", "苦", "无力", "窒息",
)


# ───────────────────────── 纯逻辑（无 DB / 无 LLM，可独立单测） ─────────────────────────

def scan_cliches(texts: list[str]) -> list[str]:
    """
    统计套话在近章正文中的命中分布，返回应禁用的套话展示串（按热度降序）。

    判定为「高频」的阈值：命中 ≥ 2 个不同章节，或总命中 ≥ 4 次。
    这样只锁定真正反复出现的腔调，避免误伤偶发用词。

    Args:
        texts: 近 N 章的纯文本正文（已去 HTML），每元素为一章。

    Returns:
        形如 ["嘴角勾起 / 一抹弧度（近3章共7次）", ...] 的列表；无高频则为 []。
    """
    flagged: list[tuple[str, int, int]] = []
    for name, pat in _CLICHE_PATTERNS:
        rx = re.compile(pat)
        total = 0
        chapters_hit = 0
        for t in texts:
            n = len(rx.findall(t or ""))
            if n:
                chapters_hit += 1
                total += n
        if chapters_hit >= 2 or total >= 4:
            flagged.append((name, total, chapters_hit))
    flagged.sort(key=lambda x: (-x[1], -x[2]))
    return [f"{name}（近{ch}章共{tot}次）" for name, tot, ch in flagged]


def scan_sentence_openers(
    texts: list[str], top_n: int = 4, min_total: int = 5
) -> list[str]:
    """
    统计跨章高频「句首三字」，揪出 AI 偏好的固定开头（如「他知道」「就在这」）。

    Args:
        texts: 近 N 章纯文本。
        top_n: 最多返回几个高频句首。
        min_total: 句首出现总次数达到此值才纳入。

    Returns:
        形如 ["「他知道…」（8次）", ...]；无则 []。
    """
    counter: Counter[str] = Counter()
    for t in texts:
        for seg in _SENT_SPLIT.split(t or ""):
            seg = seg.strip()
            if len(seg) < 4:
                continue
            if _HEAD_SKIP.match(seg):
                continue
            counter[seg[:3]] += 1
    out: list[str] = []
    for head, cnt in counter.most_common(20):
        if cnt >= min_total:
            out.append(f"「{head}…」（{cnt}次）")
        if len(out) >= top_n:
            break
    return out


def count_consecutive_depressive(tones: list[str]) -> int:
    """
    统计「最近一段连续憋屈基调」的章数。

    Args:
        tones: 章级情感基调，按章序升序（最新的在末尾，含当前章）。

    Returns:
        末尾连续命中憋屈关键词的章数；0 表示当前不在憋屈连段中。
    """
    cnt = 0
    for tone in reversed(tones):
        if tone and any(k in tone for k in _DEPRESSIVE_TONE_KEYS):
            cnt += 1
        else:
            break
    return cnt


# ───────────────────────── DB 取数 + 组装（运行期使用） ─────────────────────────

def _recent_chapter_texts(
    db: "Session", project_id: str, chapter: "Chapter"
) -> list[str]:
    """取当前章之前最近 N 章的纯文本正文（升序返回）。"""
    from app.models import Chapter as ChapterModel
    from app.routers.ai.text_utils import plain_text

    rows = (
        db.query(ChapterModel)
        .filter(
            ChapterModel.project_id == project_id,
            ChapterModel.sort_order < chapter.sort_order,
        )
        .order_by(ChapterModel.sort_order.desc())
        .limit(_RECENT_CHAPTER_WINDOW)
        .all()
    )
    texts: list[str] = []
    for row in rows:
        body = plain_text(row.content or "")
        if body and len(body) >= _MIN_CHAPTER_CHARS:
            texts.append(body)
    texts.reverse()  # 升序：旧 → 新
    return texts


def build_anti_ai_tic_block(
    db: "Session", project_id: str, chapter: "Chapter"
) -> str:
    """读近章正文，组装「反 AI 腔·本章禁用套话」块（无高频套话则返回 ""）。"""
    texts = _recent_chapter_texts(db, project_id, chapter)
    if not texts:
        return ""
    cliches = scan_cliches(texts)
    openers = scan_sentence_openers(texts)
    if not cliches and not openers:
        return ""

    lines = ["▍反 AI 腔·本章硬约束（基于近章正文统计，违反即重写）"]
    if cliches:
        lines.append("· 本章禁止再用以下已被用滥的套话/换更具体的写法：")
        lines.append("  " + "；".join(cliches[:8]))
    if openers:
        lines.append("· 以下句首已高频，本章句子开头需主动变换、避免雷同：")
        lines.append("  " + "、".join(openers))
    lines.append(
        "· 通则：用具体动作、对话、感官细节代替抽象套话与心理总结；"
        "同一比喻/口头禅本章不重复使用。"
    )
    return "\n".join(lines)


def build_emotion_budget_block(
    db: "Session",
    project_id: str,
    chapter: "Chapter",
    outline_node: "OutlineNode | None",
) -> str:
    """
    基于近章 + 本章 ``OutlineNode.emotional_tone`` 统计连续憋屈，超阈值则要求插小爽点。

    阈值：连续憋屈（含本章）≥ 2 章触发提醒；≥ 3 章升级为硬要求。
    """
    from app.models import Chapter as ChapterModel
    from app.models import OutlineNode as OutlineNodeModel

    rows = (
        db.query(ChapterModel)
        .filter(
            ChapterModel.project_id == project_id,
            ChapterModel.sort_order < chapter.sort_order,
        )
        .order_by(ChapterModel.sort_order.desc())
        .limit(_RECENT_CHAPTER_WINDOW)
        .all()
    )
    rows.reverse()  # 升序

    node_ids = [r.outline_node_id for r in rows if r.outline_node_id]
    tone_by_node: dict = {}
    if node_ids:
        for node in (
            db.query(OutlineNodeModel)
            .filter(OutlineNodeModel.id.in_(node_ids))
            .all()
        ):
            tone_by_node[node.id] = (node.emotional_tone or "").strip()

    tones: list[str] = [tone_by_node.get(r.outline_node_id, "") for r in rows]
    cur_tone = (outline_node.emotional_tone or "").strip() if outline_node else ""
    tones.append(cur_tone)

    streak = count_consecutive_depressive(tones)
    if streak < 2:
        return ""

    if streak >= 3:
        return (
            "▍情绪预算·硬约束\n"
            f"· 警告：含本章已连续 {streak} 章为憋屈/压抑基调，番茄读者将批量弃书。\n"
            "· 本章必须给出一次明确的小爽点/反转/出口（哪怕局部胜利、扳回一城、"
            "获得关键信息），让读者看到希望；禁止继续纯憋屈推进。"
        )
    return (
        "▍情绪预算·提醒\n"
        f"· 含本章已连续 {streak} 章偏憋屈，建议本章安排一处情绪释放或小爽点，"
        "避免压抑过载导致弃书；若剧情确需继续压抑，章末务必留强反弹钩子。"
    )


def build_draft_style_guard_block(
    db: "Session",
    project_id: str,
    chapter: "Chapter",
    outline_node: "OutlineNode | None",
) -> str:
    """
    组装写章风格守门块（反 AI 腔 + 情绪预算），纯文本注入 draft prompt。

    无可注入内容（近章为空 / 无高频套话 / 情绪正常）时返回 ""，不产生空白块。
    """
    parts: list[str] = []
    tic = build_anti_ai_tic_block(db, project_id, chapter)
    if tic:
        parts.append(tic)
    budget = build_emotion_budget_block(db, project_id, chapter, outline_node)
    if budget:
        parts.append(budget)
    return "\n\n".join(parts)
