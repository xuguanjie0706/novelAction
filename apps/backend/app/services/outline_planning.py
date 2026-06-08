from __future__ import annotations

import math
from typing import Iterable, Sequence, TypeVar


MIN_CHAPTERS_PER_VOLUME = 30
TARGET_CHAPTERS_PER_VOLUME = 60
TARGET_WORDS_PER_CHAPTER = 2300
WORD_ESTIMATE_RANGE = (2200, 2400)

# 总章数下限；字数按每章 TARGET_WORDS_PER_CHAPTER（2300）估算（与 ai_service 文案一致）
SCALE_TARGET_TOTAL_CHAPTERS = {
    "micro": 180,   # 约 41 万字 → 超短篇目标约 40 万字
    "auto": 540,
    "short": 360,
    "medium": 540,
    "long": 660,
    "epic": 870,    # 约 200 万字
}

T = TypeVar("T")

# --------------------------------------------------------------------------
# target_words 驱动的推算函数（单一数据源）
# --------------------------------------------------------------------------

def words_to_plan(target_words: int) -> dict:
    """从目标字数推算章数、卷数。

    返回:
        total_chapters: 总章数
        total_volumes:  建议卷数
        chapters_last:  最后一卷章数（可能 < 60）
        scale_label:    对应的规模标签（仅用于 UI 显示，不参与计算）
    """
    tw = max(int(target_words or 1_200_000), MIN_CHAPTERS_PER_VOLUME * TARGET_WORDS_PER_CHAPTER)
    total_chapters = round(tw / TARGET_WORDS_PER_CHAPTER)
    full_volumes, remainder = divmod(total_chapters, TARGET_CHAPTERS_PER_VOLUME)
    # 余数不足半卷（30章）时并入前一卷；否则独立成卷
    if remainder == 0:
        total_volumes = full_volumes
        chapters_last = TARGET_CHAPTERS_PER_VOLUME
    elif remainder < MIN_CHAPTERS_PER_VOLUME:
        total_volumes = max(1, full_volumes)
        chapters_last = TARGET_CHAPTERS_PER_VOLUME + remainder  # 最后一卷略超 60，后续 split 会拆
    else:
        total_volumes = full_volumes + 1
        chapters_last = remainder

    # 推断标签（仅显示用）
    if tw <= 500_000:
        scale_label = "micro"
    elif tw <= 900_000:
        scale_label = "short"
    elif tw <= 1_400_000:
        scale_label = "medium"
    elif tw <= 1_700_000:
        scale_label = "long"
    else:
        scale_label = "epic"

    return {
        "total_chapters": total_chapters,
        "total_volumes": total_volumes,
        "chapters_last": chapters_last,
        "scale_label": scale_label,
    }


def doupo_volume_chapter_plan(target_words: int) -> dict:
    """斗破线卷章配额：与 ``words_to_plan`` 共用总章数/总卷数，按卷拆分 planned_chapters。

    规则（斗破/大白文爽文推荐）：
    - **第 1 卷 30 章**：开局钩子密、节奏快，不宜拖长；
    - **第 2～N-1 卷各 60 章**：与 ``TARGET_CHAPTERS_PER_VOLUME`` 一致；
    - **末卷**：剩余章数（可能 >60，如全书仅 2 卷时第二卷会偏长）。

    各卷之和严格等于 ``total_chapters``。
    """
    tw = max(int(target_words or 1_200_000), MIN_CHAPTERS_PER_VOLUME * TARGET_WORDS_PER_CHAPTER)
    base = words_to_plan(tw)
    total_chapters = base["total_chapters"]
    n = base["total_volumes"]

    if n <= 1:
        quotas = [total_chapters]
    elif n == 2:
        first = min(MIN_CHAPTERS_PER_VOLUME, total_chapters - MIN_CHAPTERS_PER_VOLUME)
        quotas = [first, total_chapters - first]
    else:
        quotas = [MIN_CHAPTERS_PER_VOLUME]
        quotas.extend([TARGET_CHAPTERS_PER_VOLUME] * (n - 2))
        last = total_chapters - sum(quotas)
        if last < MIN_CHAPTERS_PER_VOLUME:
            deficit = MIN_CHAPTERS_PER_VOLUME - last
            quotas[-1] = max(MIN_CHAPTERS_PER_VOLUME, quotas[-1] - deficit)
            last = total_chapters - sum(quotas)
        quotas.append(last)

    assert sum(quotas) == total_chapters, (quotas, total_chapters, tw)
    return {**base, "target_words": tw, "chapter_quotas": quotas}


def target_total_chapters_from_words(target_words: int) -> int:
    """直接返回总章数下限（用于 normalize_volume_plan）。"""
    return words_to_plan(target_words)["total_chapters"]


def target_total_chapters(scale_hint: str) -> int:
    """兼容旧调用：通过 scale_hint 查表。"""
    return SCALE_TARGET_TOTAL_CHAPTERS.get(scale_hint, SCALE_TARGET_TOTAL_CHAPTERS["auto"])


def normalize_chapter_count(value: object, minimum: int = MIN_CHAPTERS_PER_VOLUME) -> int:
    if not isinstance(value, int) or value < 1:
        return minimum
    rounded_units = math.floor(value / MIN_CHAPTERS_PER_VOLUME + 0.5)
    return max(minimum, rounded_units * MIN_CHAPTERS_PER_VOLUME)


def _split_volume(vol: dict) -> list[dict]:
    planned = normalize_chapter_count(vol.get("planned_chapters"))
    chunks: list[int] = []
    remaining = planned
    while remaining > 0:
        chunk = min(TARGET_CHAPTERS_PER_VOLUME, remaining)
        chunks.append(chunk)
        remaining -= chunk

    if len(chunks) == 1:
        return [{**vol, "planned_chapters": chunks[0]}]

    title = str(vol.get("title") or "未命名卷")
    numerals = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    return [
        {
            **vol,
            "title": f"{title}（{numerals[idx] if idx < len(numerals) else idx + 1}）",
            "planned_chapters": chunk,
        }
        for idx, chunk in enumerate(chunks)
    ]


def normalize_volume_plan(
    volumes: list[dict],
    scale_hint: str = "auto",
    target_words: int | None = None,
) -> list[dict]:
    """标准化卷规划。

    优先使用 target_words 计算总章数下限；
    若未提供则回退到 scale_hint 查表（向后兼容）。
    """
    normalized = [
        {**vol, "planned_chapters": normalize_chapter_count(vol.get("planned_chapters"))}
        for vol in volumes
    ]
    if not normalized:
        return normalized

    if target_words:
        minimum_total = target_total_chapters_from_words(target_words)
    else:
        minimum_total = target_total_chapters(scale_hint)

    current_total = sum(vol["planned_chapters"] for vol in normalized)
    if current_total < minimum_total:
        missing = minimum_total - current_total
        extra = math.ceil(missing / MIN_CHAPTERS_PER_VOLUME) * MIN_CHAPTERS_PER_VOLUME
        last = normalized[-1]
        normalized[-1] = {
            **last,
            "planned_chapters": last["planned_chapters"] + extra,
        }

    split: list[dict] = []
    for vol in normalized:
        split.extend(_split_volume(vol))
    return split


def chunk_by_volume(items: Sequence[T], size: int = TARGET_CHAPTERS_PER_VOLUME) -> Iterable[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


# --------------------------------------------------------------------------
# 章节字数预算（按阶段动态计算）
# --------------------------------------------------------------------------

def chapter_word_budget_for_phase(
    phase: str,
    pacing: str = "normal",
    has_face_slap: bool = False,
    has_emotional_beat: bool = False,
    is_fanqie: bool = False,
) -> int:
    """按叙事阶段+节奏标记计算章节预期字数。

    设计动机：打破"全书一律2200字"的平线感，让字数配合叙事节奏呼吸。
    climax 章需要展开空间，dark_hour 情感章需要内心戏字数，
    opening fast 章节短促有力不拖沓。

    番茄模式（is_fanqie=True）：基线设为 2000-2600，硬上限 2800、下限 1900。
    番茄仍偏好短章（高翻页率 = 高完读率），但原 1500 级基线偏短，叠加 plain
    直白风格后正文常掉到 1100-1300，故整体上调一档：开局 ~2000、其余 2200-2500。

    Args:
        phase: 卷阶段（opening/rising/turning/dark_hour/climax/ending）。
        pacing: 章节节奏（fast/normal/slow/climax）。
        has_face_slap: 本章有打脸场景，需要更多铺垫展开。
        has_emotional_beat: 本章有情感高点，需要内心戏字数。
        is_fanqie: 番茄模式（pace_type=="fast"）。

    Returns:
        预期字数。标准模式 [1800, 3500]，番茄模式 [1900, 2800]。
    """
    if is_fanqie:
        base = {
            "opening": 2000, "rising": 2300, "turning": 2400,
            "dark_hour": 2400, "climax": 2600, "ending": 2200,
        }.get(phase, 2300)
        pacing_mod = {"fast": -100, "slow": 150, "climax": 200, "normal": 0}.get(pacing, 0)
        slap_mod = 150 if has_face_slap else 0
        emotion_mod = 150 if has_emotional_beat else 0
        return min(2800, max(1900, base + pacing_mod + slap_mod + emotion_mod))

    base = {
        "opening": 2200,
        "rising": 2300,
        "turning": 2400,
        "dark_hour": 2700,
        "climax": 3000,
        "ending": 2200,
    }.get(phase, TARGET_WORDS_PER_CHAPTER)

    pacing_mod = {"fast": -200, "slow": 200, "climax": 500, "normal": 0}.get(pacing, 0)
    slap_mod = 200 if has_face_slap else 0
    emotion_mod = 200 if has_emotional_beat else 0

    return min(3500, max(1800, base + pacing_mod + slap_mod + emotion_mod))


def resolve_chapter_expected_words(
    ai_words: object,
    dynamic_words: int,
    *,
    is_fanqie: bool = False,
) -> int:
    """章纲落库字数：``chapter_word_budget_for_phase`` 为下限，AI 可更高但不得压低。

    设计动机：番茄 prompt 仍常输出 1500 级 expected_words；若直接采用会导致
    plain 写章正文系统性偏短。动态预算已含 phase/pacing/爽点修正，取 max 对齐。
    """
    lo = 1900 if is_fanqie else 1800
    hi = 4000
    if isinstance(ai_words, int) and lo <= ai_words <= hi:
        return max(ai_words, dynamic_words)
    return dynamic_words


def resolve_draft_word_target(
    word_target: int,
    *,
    phase: str = "",
    writing_style: str = "standard",
    is_fanqie: bool = False,
) -> int:
    """写章正文字数目标：章纲 expected_words 与阶段/风格硬下限取 max。

    plain + opening 叠加后仍常低于 prompt 要求；此处统一抬升，避免「要 1900 写出 1100」。
    """
    base = max(1900 if is_fanqie else 1800, int(word_target or TARGET_WORDS_PER_CHAPTER))
    phase_norm = (phase or "").strip().lower()
    style = (writing_style or "standard").strip().lower()
    if phase_norm == "opening":
        base = max(base, 2100 if style == "plain" else 2200)
    elif style == "plain":
        base = max(base, 2000)
    return base


def build_book_budget_block(
    target_words: int,
    total_chapters: int,
    total_volumes: int,
    volume_quota: int,
    chapters_used_so_far: int = 0,
    batch_start: int | None = None,
    batch_end: int | None = None,
) -> str:
    """生成注入 chapter plan prompt 的全书预算约束块。

    把全书目标、已用配额、本卷配额、本批任务数显式写入 prompt，
    防止 AI 在跨卷/跨批生成时漂移章节数量。

    Args:
        target_words: 全书目标字数（项目硬锚点）。
        total_chapters: 全书目标总章数（由 words_to_plan 计算）。
        total_volumes: 全书卷数。
        volume_quota: 本卷配额章数（planned_chapters，卷级大纲锁定）。
        chapters_used_so_far: 此前所有卷已落库的章节数。
        batch_start: 本批起始章号（1-based，相对本卷）。
        batch_end: 本批结束章号（1-based，相对本卷）。

    Returns:
        可直接拼入 prompt 的多行约束文字块。
    """
    approx_wan = round(target_words / 10_000)
    remaining_global = total_chapters - chapters_used_so_far
    lines = [
        "\n【全书字数预算（硬性约束，不得漂移）】",
        f"  全书目标：{target_words:,}字（约{approx_wan}万字）/ 共{total_chapters}章 / {total_volumes}卷",
        f"  已规划章数：{chapters_used_so_far}章，全书剩余配额：{remaining_global}章",
        f"  本卷配额：{volume_quota}章（卷级大纲锁定，不得多生成也不得少生成）",
    ]
    if batch_start is not None and batch_end is not None:
        batch_count = batch_end - batch_start + 1
        lines.append(
            f"  本批任务：第{batch_start}～{batch_end}章，"
            f"必须恰好返回{batch_count}个章节（JSON数组长度={batch_count}）"
        )
    lines += [
        "  ⚠️ 返回JSON数组长度必须严格等于本批任务章数，不得多也不得少",
        "  ⚠️ expected_words 按阶段参考值填写，禁止全部写同一个数字",
    ]
    return "\n".join(lines)
