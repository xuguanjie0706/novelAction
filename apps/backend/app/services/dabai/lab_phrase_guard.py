"""近章高频表达守卫 + 见证者反应模式轮换。

写章前从近 N 章正文抽取套话/重复片段，注入「本章禁用」块；
分场/正文 prompt 用模式轮换替代硬编码「愣住→心服」阶梯。
"""
from __future__ import annotations

import re
from collections import Counter
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline

# 爽文 AI 高频套话（出现即计入近章禁词候选）
_CLICHE_FRAGMENTS: tuple[str, ...] = (
    "阴寒灵力", "轰然倒灌", "微微颤动", "万魂幡微微", "不敢置信",
    "如坠冰窟", "倒吸一口凉气", "眼珠子都要", "眼珠子都快", "满脸敬畏",
    "排山倒海", "血液都要冻结", "吓得一哆嗦", "宛如实质", "腥甜的气味",
    "嗤嗤的腐蚀", "低声议论", "面不改色", "冷笑一声", "浑身一震",
    "众人先是一愣", "随即震惊", "半天爬不起来",
)

WITNESS_REACTION_MODES: dict[int, str] = {
    1: "①愣住→不信→震惊→心服",
    2: "②嗤笑→脸僵→冷汗→噤声",
    3: "③围观起哄→骚动→倒抽冷气→鸦雀无声",
    4: "④笃定取胜→破绽被戳→强撑→认怂",
}


def witness_reaction_mode_index(chapter_number: int) -> int:
    """按章号轮换 1～4，避免全书同一见证者阶梯。"""
    return (max(1, int(chapter_number or 1)) - 1) % 4 + 1


def witness_reaction_mode_label(chapter_number: int) -> str:
    return WITNESS_REACTION_MODES[witness_reaction_mode_index(chapter_number)]


def _plain(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def scan_cliche_fragments(text: str) -> list[str]:
    """返回正文中命中的套话片段（去重保序）。"""
    plain = _plain(text)
    if not plain:
        return []
    seen: set[str] = set()
    hits: list[str] = []
    for frag in _CLICHE_FRAGMENTS:
        if frag in plain and frag not in seen:
            seen.add(frag)
            hits.append(frag)
    return hits


def collect_banned_phrases(
    db: Session,
    project_id: UUID,
    before_chapter: int,
    *,
    lookback: int = 3,
    min_hits_across_corpus: int = 2,
) -> list[str]:
    """近 lookback 章正文中出现 ≥min_hits 次的套话/片段 → 本章禁用列表。"""
    if before_chapter <= 1:
        return []
    rows = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project_id,
            DabaiChapterOutline.chapter_number < before_chapter,
            DabaiChapterOutline.chapter_number >= before_chapter - lookback,
        )
        .order_by(DabaiChapterOutline.chapter_number.desc())
        .all()
    )
    counter: Counter[str] = Counter()
    for row in rows:
        for frag in scan_cliche_fragments(row.content or ""):
            counter[frag] += 1
    banned = [p for p, n in counter.items() if n >= min_hits_across_corpus]
    banned.sort(key=lambda p: (-counter[p], p))
    return banned[:12]


def check_chapter_phrase_violations(
    db: Session,
    project_id: UUID,
    chapter_number: int,
    content: str,
) -> list[str]:
    """规则层：本章正文命中近章禁词列表的片段。"""
    banned = collect_banned_phrases(db, project_id, chapter_number)
    plain = _plain(content)
    return [p for p in banned if p in plain]


def build_phrase_guard_block(
    db: Session,
    project_id: UUID,
    before_chapter: int,
    *,
    lookback: int = 3,
) -> str:
    """写章 user 注入：近章已用表达，本章须换说法或改物件/动作反应。"""
    banned = collect_banned_phrases(
        db, project_id, before_chapter, lookback=lookback,
    )
    if not banned:
        mode = witness_reaction_mode_label(before_chapter)
        return (
            f"【表达多样化（硬）】本章见证者默认反应模式：{mode}；"
            "优先物件/动作/空间转义，禁止套话「不敢置信/如坠冰窟/眼珠子都要掉出来」。"
        )
    lines = [
        "【近章已用表达 · 本章禁用复述】",
        "下列短语在近章正文已反复出现，本章须换说法或改用物件/动作/空间反应，禁止原样再用：",
    ]
    lines.extend(f"  - {p}" for p in banned)
    lines.append(
        f"见证者反应模式本章优先：{witness_reaction_mode_label(before_chapter)}；"
        "同一人物勿复制近章相同反应句。"
    )
    return "\n".join(lines)


def format_witness_reaction_instruction(
    chapter_number: int,
    witness_reactions: list[dict] | None = None,
) -> str:
    """分场块末尾：按人分配反应模式，替代硬编码单一阶梯。"""
    if isinstance(witness_reactions, list) and witness_reactions:
        lines = ["  【见证者反应（按人分配，勿全员同一模板）】"]
        for item in witness_reactions[:8]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            mode = int(item.get("mode") or witness_reaction_mode_index(chapter_number))
            beats = item.get("beats") or item.get("reaction_beats") or []
            if isinstance(beats, list) and beats:
                beat_s = "→".join(str(b).strip() for b in beats[:4] if str(b).strip())
            else:
                beat_s = WITNESS_REACTION_MODES.get(mode, witness_reaction_mode_label(chapter_number))
            lines.append(f"    - {name}：模式{mode}（{beat_s}）")
        lines.append(
            "  反应须落到具体动作/物件/空间细节，禁止写「不敢置信/如坠冰窟/眼珠子都要掉出来」。"
        )
        return "\n".join(lines)
    mode = witness_reaction_mode_label(chapter_number)
    return (
        f"  【见证者反应】本章默认模式 {mode}；"
        "优先物件/动作/空间转义；禁止套话「不敢置信/如坠冰窟/眼珠子都要掉出来」；"
        "同一见证者近章已用过的反应句本章禁用。"
    )
