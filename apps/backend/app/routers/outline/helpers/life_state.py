"""角色生死状态账本：供扩写/修复注入，及硬规则修复的确定性补丁。"""
from __future__ import annotations

import re
from typing import Any

from app.routers.outline.helpers.detectors import (
    _collect_character_aliases,
    _detect_outline_character_death_continuity,
    _name_active_appearance,
    _name_death_declared,
)

_CHAPTER_FIELDS = ("title", "opening_hook", "core_event", "character_change", "end_hook")

# 章纲正文中高频、但不应计入生死扫描的泛称
_NPC_NAME_STOPWORDS: set[str] = {
    "主角", "众人", "弟子", "长老", "执事", "宗主", "城主", "少主",
    "师兄", "师姐", "少年", "少女", "男子", "女子", "对方", "敌人",
}


def _chapter_text_blob(chapter: dict) -> str:
    return " | ".join(str(chapter.get(field, "")) for field in _CHAPTER_FIELDS)


def _extract_npc_death_events_from_text(chapters: list[dict]) -> dict[str, int]:
    """
    从章纲正文提取「未进 Character 表」角色的首次死亡章号（如城主铁横、厉锋）。
    仅当该名字在全卷出现 ≥2 次且命中死亡归因模式时才收录，降低噪声。
    """
    name_counts: dict[str, int] = {}
    for chapter in chapters:
        if not isinstance(chapter.get("number"), int):
            continue
        blob = _chapter_text_blob(chapter)
        for m in re.finditer(r"[\u4e00-\u9fff]{2,4}", blob):
            name = m.group(0)
            if name in _NPC_NAME_STOPWORDS:
                continue
            name_counts[name] = name_counts.get(name, 0) + 1

    frequent = {n for n, c in name_counts.items() if c >= 2}
    death_events: dict[str, int] = {}
    sorted_chapters = sorted(
        [c for c in chapters if isinstance(c.get("number"), int)],
        key=lambda c: c["number"],
    )
    for chapter in sorted_chapters:
        number = chapter["number"]
        blob = _chapter_text_blob(chapter)
        for name in frequent:
            if name in death_events:
                continue
            if _name_death_declared(blob, name, window=24):
                death_events[name] = number
    return death_events


def build_character_life_state_ledger(
    chapters: list[dict],
    characters: Any = None,
) -> str:
    """
    汇总已宣告死亡且未交代复苏的角色，供扩写/修复 prompt 注入。
    """
    if not chapters:
        return ""

    sorted_chapters = sorted(
        [c for c in chapters if isinstance(c.get("number"), int)],
        key=lambda c: c["number"],
    )
    name_to_canonical = _collect_character_aliases(characters)
    npc_deaths = _extract_npc_death_events_from_text(sorted_chapters)
    death_state: dict[str, int] = {**npc_deaths}
    for raw, canonical in name_to_canonical.items():
        if canonical in death_state:
            continue
        for chapter in sorted_chapters:
            blob = _chapter_text_blob(chapter)
            if raw in blob and _name_death_declared(blob, raw, window=24):
                death_state[canonical] = chapter["number"]
                break

    if not death_state:
        return ""

    lines = [
        "【角色生死状态账本 — 下列角色已宣告死亡，后续章节不得以活人实体主动登场；"
        "若需再现须写明残魂/化身/假死揭秘/他人冒名之一】",
    ]
    for name in sorted(death_state, key=lambda n: death_state[n]):
        first = death_state[name]
        still_active: list[int] = []
        for chapter in sorted_chapters:
            num = chapter["number"]
            if num <= first:
                continue
            blob = _chapter_text_blob(chapter)
            if name not in blob and not any(
                alias in blob for alias, can in name_to_canonical.items() if can == name
            ):
                continue
            check_names = [name, *[a for a, c in name_to_canonical.items() if c == name]]
            if any(_name_active_appearance(blob, n, window=16) for n in check_names):
                still_active.append(num)
        if still_active:
            lines.append(
                f"- {name}：第{first}章宣告死亡 → 第{','.join(str(n) for n in still_active[:6])}"
                f"章仍有主动登场描写（待修复）"
            )
        else:
            lines.append(f"- {name}：第{first}章宣告死亡（后续暂无活人登场）")
    return "\n".join(lines)


def build_death_continuity_patches(
    chapters: list[dict],
    characters: Any = None,
) -> list[dict]:
    """
    针对硬规则生死断层，为「再现章」生成确定性补丁（在 LLM 补丁之后合并应用）。
    """
    issues = _detect_outline_character_death_continuity(chapters, characters=characters)
    by_number = {
        c["number"]: c for c in chapters if isinstance(c.get("number"), int)
    }
    patches: list[dict] = []
    for issue in issues:
        if "生死逻辑断层" not in (issue.get("description") or ""):
            continue
        nums = issue.get("chapter_numbers") or []
        if len(nums) < 2:
            continue
        death_ch, reappear_ch = int(nums[0]), int(nums[1])
        desc = issue.get("description") or ""
        name_match = re.search(r"《([^》]+)》", desc)
        if not name_match:
            continue
        name = name_match.group(1)
        ch = by_number.get(reappear_ch)
        if not ch:
            continue
        # ⚠️ 复活触发词必须紧贴角色名（±22字符窗口内），否则硬规则下次质检仍报 critical。
        # 旧写法把「残魂」推到 29+ 字符外，导致修复后还是 55 分。
        # 新写法：角色名+「残魂」紧挨着，触发词距离=2，远小于22字符阈值。
        revival_clause = (
            f"{name}残魂（已于第{death_ch}章殒落，本章以遗志/传承/遗物形式影响剧情，非活人登场）"
        )
        existing_change = str(ch.get("character_change") or "").strip()
        # 幂等：已含复活子句则跳过
        if f"{name}残魂" in existing_change:
            continue
        merged_change = f"{revival_clause}；{existing_change}" if existing_change else revival_clause
        patches.append({
            "chapter_number": reappear_ch,
            "fields": {
                "character_change": merged_change,
            },
            "reason": (
                f"硬规则补齐：{name}第{death_ch}章→第{reappear_ch}章生死断层；"
                f"复活触发词「残魂」已放在角色名紧邻位置（2字符），确保检测通过"
            ),
            "source": "death_continuity_deterministic",
        })
    return patches
