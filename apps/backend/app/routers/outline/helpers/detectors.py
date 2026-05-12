"""大纲确定性子检测：战力曲线、死亡连续性、主题对齐、伏笔台账。"""
from __future__ import annotations

from app.routers.outline.helpers.constants import (
    CHARACTER_ACTIVE_APPEARANCE_VERBS,
    CHARACTER_DEATH_MARKERS,
    CHARACTER_REVIVAL_TRIGGERS,
    DESTINY_REVEAL_PATTERNS,
    PROTAGONIST_CONTEXT_HINTS,
    REALM_REGRESSION_TRIGGER_WORDS,
    SELF_DETERMINATION_THEME_KEYWORDS,
)
from app.routers.outline.helpers.realm_timeline import (
    _build_realm_rank_map,
    _extract_protagonist_realm_rank,
)

def _detect_outline_power_curve_issues(
    chapters: list[dict],
    *,
    power_systems,
    scope: str = "volume",
    protagonist_names: list[str] | None = None,
) -> list[dict]:
    """
    战力曲线确定性校验：
      1. 主角境界回落 ≥ 2 级 但 character_change 未交代代价 → high。
      2. 在书级范围下，主角已抵达终点境界但剩余章节 > 25%（且总章 > 60）→ high pacing。
    """
    if not power_systems:
        return []
    name_to_rank, max_system_rank, declared_end_rank = _build_realm_rank_map(power_systems)
    if not name_to_rank:
        return []

    sorted_chapters = sorted(
        [c for c in chapters if isinstance(c.get("number"), int)],
        key=lambda c: c["number"],
    )
    total_chapters = len(sorted_chapters)
    if total_chapters == 0:
        return []

    issues: list[dict] = []
    running_max = 0
    last_peak_chapter: int | None = None
    for chapter in sorted_chapters:
        rank = _extract_protagonist_realm_rank(
            chapter, name_to_rank, protagonist_names=protagonist_names,
        )
        if rank is None:
            continue
        number = chapter["number"]
        change_text = str(chapter.get("character_change") or "")
        has_trigger = any(trig in change_text for trig in REALM_REGRESSION_TRIGGER_WORDS)
        if rank + 2 <= running_max and not has_trigger:
            issues.append({
                "severity": "high",
                "type": "continuity",
                "chapter_numbers": [number],
                "description": (
                    f"第{number}章主角境界回落到 rank{rank}（character_change 提及），"
                    f"但前文最高已达 rank{running_max}，本章未在 character_change 交代"
                    "跌落/重伤/反噬/封印/透支寿元等代价机制，属于无解释的境界倒退。"
                ),
                "suggested_patch": {
                    "chapter_number": number,
                    "field": "character_change",
                    "replacement": "",
                },
            })
        if rank > running_max:
            running_max = rank
            last_peak_chapter = number

    if scope == "book" and last_peak_chapter is not None and total_chapters >= 60:
        target_end_rank = declared_end_rank if declared_end_rank else max_system_rank
        if target_end_rank and running_max >= target_end_rank:
            remaining = total_chapters - last_peak_chapter
            remaining_ratio = remaining / total_chapters if total_chapters else 0
            if remaining_ratio > 0.25:
                issues.append({
                    "severity": "high",
                    "type": "pacing",
                    "chapter_numbers": [last_peak_chapter],
                    "description": (
                        f"第{last_peak_chapter}章主角境界已达 rank{running_max}"
                        f"（接近/达到终点 rank{target_end_rank}），但全书剩余 {remaining} 章"
                        f"（约 {remaining_ratio:.0%}），后期境界提升空间已耗尽，"
                        "必然导致跨地图速刷或重复刷怪。建议放缓中段境界推进，"
                        "或在大纲规划层（plan_full_structure）扩展终点境界与卷数。"
                    ),
                    "suggested_patch": {
                        "chapter_number": last_peak_chapter,
                        "field": "core_event",
                        "replacement": "",
                    },
                })

    return issues


def _name_near_marker(text: str, name: str, markers, window: int = 18) -> bool:
    """检查 text 中 name 出现位置 ±window 字符内是否有任一 marker。"""
    if not name or not text:
        return False
    pos = 0
    while True:
        i = text.find(name, pos)
        if i == -1:
            return False
        snippet = text[max(0, i - window): i + len(name) + window]
        for m in markers:
            if m and m in snippet:
                return True
        pos = i + len(name)


def _collect_character_aliases(characters) -> dict[str, str]:
    """构造 {name_or_alias: canonical_name} 映射；按长度降序排序便于后续优先匹配长名。"""
    name_to_canonical: dict[str, str] = {}
    for char in characters or []:
        canonical = (getattr(char, "name", None) or "").strip()
        if not canonical:
            continue
        name_to_canonical[canonical] = canonical
        aliases = getattr(char, "alias", None)
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str):
                    a = alias.strip()
                    if a and a not in name_to_canonical:
                        name_to_canonical[a] = canonical
    return name_to_canonical


def _detect_outline_character_death_continuity(
    chapters: list[dict],
    *,
    characters,
) -> list[dict]:
    """
    检测角色死亡后无机制再次主动登场。
    判断流程（按章节顺序）：
      1. 章节文本中角色名 ±18 字符内出现死亡词 → 标记该角色为已宣告死亡。
      2. 已宣告死亡的角色，若后续章节出现复活类触发词 → 视为机制说明，重置警戒。
      3. 已宣告死亡且未交代复活时，再次出现主动登场动词 → critical issue。
    仅扫描 core_event/character_change/end_hook 等剧情字段，不扫描 foreshadow（伏笔
    可以提及死者而不构成实际登场）。
    """
    if not characters:
        return []
    name_to_canonical = _collect_character_aliases(characters)
    if not name_to_canonical:
        return []

    sorted_chapters = sorted(
        [c for c in chapters if isinstance(c.get("number"), int)],
        key=lambda c: c["number"],
    )

    death_state: dict[str, int] = {}     # canonical -> first death chapter
    explained_after: dict[str, int] = {}  # canonical -> chapter where revival explained
    issues: list[dict] = []
    seen_pair: set[tuple[str, int]] = set()

    # 长名优先匹配，避免 "鬼手长老" 命中 "鬼手"
    sorted_names = sorted(name_to_canonical.keys(), key=len, reverse=True)

    for chapter in sorted_chapters:
        number = chapter["number"]
        text_blob = " | ".join(
            str(chapter.get(field, ""))
            for field in ("title", "opening_hook", "core_event", "character_change", "end_hook")
        )
        if not text_blob:
            continue

        for raw_name in sorted_names:
            canonical = name_to_canonical[raw_name]
            if raw_name not in text_blob:
                continue

            # 1) 死亡宣告
            if canonical not in death_state:
                if _name_near_marker(text_blob, raw_name, CHARACTER_DEATH_MARKERS, window=22):
                    death_state[canonical] = number
                continue

            # 2) 已死亡，本章是否给出复活机制
            if canonical not in explained_after:
                if _name_near_marker(text_blob, raw_name, CHARACTER_REVIVAL_TRIGGERS, window=22):
                    explained_after[canonical] = number
                    continue
                # 3) 检测主动登场
                if _name_near_marker(text_blob, raw_name, CHARACTER_ACTIVE_APPEARANCE_VERBS, window=14):
                    pair_key = (canonical, number)
                    if pair_key in seen_pair:
                        continue
                    seen_pair.add(pair_key)
                    issues.append({
                        "severity": "critical",
                        "type": "continuity",
                        "chapter_numbers": [death_state[canonical], number],
                        "description": (
                            f"《{canonical}》在第{death_state[canonical]}章被宣告死亡/殒落/自毁，"
                            f"但在第{number}章再次主动登场（提供道具/援助/现身/出手），"
                            "且本章未交代复活、神魂寄宿、假死、化身、传承等机制；属于角色生死逻辑断层。"
                            "建议在死亡章节加埋[残魂寄宿于X物]或在再现章节明确化身/分身/复苏触发词。"
                        ),
                        "suggested_patch": {
                            "chapter_number": number,
                            "field": "character_change",
                            "replacement": "",
                        },
                    })

    return issues


def _theme_is_self_determination(theme_statement: str, premise: str = "") -> bool:
    """判断项目主题是否属于「凡人逆袭」类。"""
    blob = f"{theme_statement or ''} || {premise or ''}"
    if not blob.strip():
        return False
    return any(kw in blob for kw in SELF_DETERMINATION_THEME_KEYWORDS)


def _detect_outline_theme_alignment_issues(
    chapters: list[dict],
    *,
    theme_statement: str = "",
    premise: str = "",
    protagonist_names: list[str] | None = None,
) -> list[dict]:
    """
    主题对齐校验：当主题属于「凡人逆袭」类时，章节中出现「完美炉胎/天选/血脉觉醒/
    转世重生/帝者血脉/圣体/道体」等揭露 + 主角指代 → medium。

    注意只扫描 core_event 与 character_change（揭露主角真实身份的字段），
    不扫描 foreshadow（埋伏笔可以提及这些词）。
    """
    if not _theme_is_self_determination(theme_statement, premise):
        return []

    sorted_chapters = sorted(
        [c for c in chapters if isinstance(c.get("number"), int)],
        key=lambda c: c["number"],
    )
    if not sorted_chapters:
        return []

    # 主角名片：优先方案（强精度）。未提供时退化为「揭露必须出现在
    # character_change 字段」的回退方案——character_change 通常描述主角变化，
    # 即便提及 NPC 也更可能是与主角相关的弧线节点。
    protagonist_set = {n.strip() for n in (protagonist_names or []) if n and isinstance(n, str)}

    issues: list[dict] = []
    seen_chapters: set[int] = set()

    for chapter in sorted_chapters:
        number = chapter["number"]
        if number in seen_chapters:
            continue
        text_blob = " | ".join(
            str(chapter.get(field, ""))
            for field in ("title", "core_event", "character_change", "end_hook")
        )
        if not text_blob:
            continue

        revealed = sorted(p for p in DESTINY_REVEAL_PATTERNS if p in text_blob)
        if not revealed:
            continue

        if protagonist_set:
            # 强精度：揭露词必须出现在主角名 ±30 字符内
            has_protagonist_marker = any(
                _name_near_marker(text_blob, name, revealed, window=30)
                for name in protagonist_set
            )
        else:
            # 回退：揭露词必须出现在 character_change 字段，或匹配窄主角指代
            char_change_text = str(chapter.get("character_change") or "")
            has_protagonist_marker = (
                any(p in char_change_text for p in revealed)
                or any(hint in text_blob for hint in PROTAGONIST_CONTEXT_HINTS)
            )
        if not has_protagonist_marker:
            continue

        seen_chapters.add(number)
        issues.append({
            "severity": "medium",
            "type": "theme_alignment",
            "chapter_numbers": [number],
            "description": (
                f"第{number}章揭示主角真实身份/起源时使用了「{('、'.join(revealed))[:80]}」类设定，"
                "把主角强大归因于「被选中/血脉/天命」，与「我命由我 / 凡人逆袭 / 草根崛起」"
                "类立意相冲突，会削弱草根爽感。"
                "建议改写为「主角原本是实验残次品 / 被弃用炉胎 / 被否定的载体」，"
                "再以后天苦修把『注定』改写成『逆天』，强化主题。"
            ),
            "suggested_patch": {
                "chapter_number": number,
                "field": "core_event",
                "replacement": "",
            },
        })

    return issues
def _detect_outline_foreshadow_issues(
    chapters: list[dict],
    *,
    foreshadows,
) -> list[dict]:
    """
    伏笔台账确定性审计（基于 Foreshadow 表）：
      1. 已过期未回收：status=open + planned_resolve_chapter < 当前最新章号 → high pacing。
      2. 高优先级长期挂账：priority>=4 + status=open + 跨度 > 100 章 → medium。
      3. 主线被弃：priority>=5 + status=dropped → high continuity。
    """
    if not foreshadows:
        return []
    sorted_chapters = sorted(
        [c.get("number") for c in chapters if isinstance(c.get("number"), int)]
    )
    if not sorted_chapters:
        return []
    latest_chapter = sorted_chapters[-1]

    issues: list[dict] = []

    for f in foreshadows:
        title = (getattr(f, "title", None) or "未命名伏笔").strip() or "未命名伏笔"
        code = (getattr(f, "code", None) or "").strip()
        label = f"{code}「{title}」" if code else f"「{title}」"
        status = (getattr(f, "status", None) or "open").strip()
        priority = getattr(f, "priority", None) or 3
        laid_no = getattr(f, "laid_chapter_number", None)
        planned_no = getattr(f, "planned_resolve_chapter", None)

        # Rule 3: critical priority dropped
        if status == "dropped" and isinstance(priority, int) and priority >= 5:
            anchor_chapter = laid_no if isinstance(laid_no, int) else latest_chapter
            issues.append({
                "severity": "high",
                "type": "continuity",
                "chapter_numbers": [anchor_chapter],
                "description": (
                    f"高优先级伏笔 {label}（priority={priority}）状态为 dropped，"
                    "属于关键主线悬念被丢弃，会让前期铺垫变成无效投入。"
                    "建议恢复 status=open 并安排在合适卷末回收，或在 character_change 中明确「悬念失效原因」。"
                ),
                "suggested_patch": {
                    "chapter_number": anchor_chapter,
                    "field": "foreshadow",
                    "replacement": "",
                },
            })
            continue

        if status != "open":
            continue

        # Rule 1: planned resolution overdue
        if isinstance(planned_no, int) and planned_no > 0 and planned_no < latest_chapter:
            issues.append({
                "severity": "high",
                "type": "pacing",
                "chapter_numbers": [planned_no],
                "description": (
                    f"伏笔 {label} 计划于第 {planned_no} 章回收，但全书已写到第 {latest_chapter} 章"
                    "仍未结清，属于已过期未回收。"
                    "建议在最近卷末追加回收章节，或显式 dropped 并交代「悬念被新冲突替代」。"
                ),
                "suggested_patch": {
                    "chapter_number": planned_no,
                    "field": "foreshadow",
                    "replacement": "",
                },
            })
            continue

        # Rule 2: high-priority long-aged open
        if (
            isinstance(priority, int)
            and priority >= 4
            and isinstance(laid_no, int)
            and laid_no > 0
            and (latest_chapter - laid_no) > 100
        ):
            issues.append({
                "severity": "medium",
                "type": "pacing",
                "chapter_numbers": [laid_no],
                "description": (
                    f"高优先级伏笔 {label}（priority={priority}）在第 {laid_no} 章埋下，"
                    f"距今已跨越 {latest_chapter - laid_no} 章仍未回收，长期挂账会让读者忘记前文铺垫。"
                    "建议在中段卷末安排显性进展（部分回收/再激活）以维持紧张感。"
                ),
                "suggested_patch": {
                    "chapter_number": laid_no,
                    "field": "foreshadow",
                    "replacement": "",
                },
            })

    return issues
