"""
realm_whitelist.py — 境界白名单构建与术语扫描

职责：
- 从 PowerSystem.levels 构建合法境界名白名单
- 构建 {境界名: rank} 映射
- 检测章节大纲中的术语脱轨（传统修真禁词 + 现代/科幻禁词）

禁止事项：不含人物境界归因逻辑（见 realm_attribution.py）。
"""
from __future__ import annotations

from app.services.xuanhuan_lexicon import (
    MODERN_BLACKLIST_FOR_XUANHUAN,
    is_xuanhuan_like_genre as _is_xuanhuan_like_genre,
)

from app.routers.outline.helpers.constants import (
    CULTIVATION_REALM_USAGE_PREFIXES,
    CULTIVATION_REALM_USAGE_SUFFIXES,
    CULTIVATION_TERM_FALSE_POSITIVE_PHRASES,
    TRADITIONAL_CULTIVATION_BLACKLIST,
)


def collect_power_system_whitelist(power_systems) -> set[str]:
    """从所有 PowerSystem.levels 抽取合法境界名（含去掉「境」后缀的简写）。"""
    whitelist: set[str] = set()
    for system in power_systems or []:
        name = (getattr(system, "name", None) or "").strip()
        if name:
            whitelist.add(name)
        levels = getattr(system, "levels", None)
        if not isinstance(levels, list):
            continue
        for level in levels:
            if not isinstance(level, dict):
                continue
            level_name = (level.get("name") or "").strip()
            if not level_name:
                continue
            whitelist.add(level_name)
            if level_name.endswith("境") and len(level_name) > 2:
                bare = level_name[:-1]
                if len(bare) >= 2:
                    whitelist.add(bare)
    return whitelist


def build_realm_rank_map(power_systems) -> tuple[dict[str, int], int | None, int | None]:
    """构造 {境界名: rank} 映射，并返回 (map, max_system_rank, declared_protagonist_end_rank)."""
    name_to_rank: dict[str, int] = {}
    max_rank = 0
    end_rank: int | None = None
    for system in power_systems or []:
        levels = getattr(system, "levels", None)
        if isinstance(levels, list):
            for level in levels:
                if not isinstance(level, dict):
                    continue
                level_name = (level.get("name") or "").strip()
                rank = level.get("rank")
                if not level_name or not isinstance(rank, int) or rank <= 0:
                    continue
                if level_name not in name_to_rank or rank > name_to_rank[level_name]:
                    name_to_rank[level_name] = rank
                if level_name.endswith("境") and len(level_name) > 2:
                    bare = level_name[:-1]
                    if len(bare) >= 2 and (bare not in name_to_rank or rank > name_to_rank[bare]):
                        name_to_rank[bare] = rank
                if rank > max_rank:
                    max_rank = rank
        declared = getattr(system, "protagonist_end_rank", None)
        if isinstance(declared, int) and declared > 0:
            end_rank = max(end_rank or 0, declared)
    return name_to_rank, (max_rank or None), end_rank


# ── 术语扫描 ─────────────────────────────────────────────────────

def _scan_banned_terms(text: str, banned: set[str]) -> set[str]:
    """现代/科幻禁词等：保持子串匹配（词表项本身不易误报）。"""
    if not text:
        return set()
    return {term for term in banned if term and term in text}


def _occurrence_inside_false_positive_phrase(
    text: str, start: int, term_len: int, phrase: str,
) -> bool:
    pos = text.find(phrase)
    while pos != -1:
        if pos <= start and start + term_len <= pos + len(phrase):
            return True
        pos = text.find(phrase, pos + 1)
    return False


def _is_cultivation_realm_term_usage(text: str, start: int, term: str) -> bool:
    """判断 term 在 start 处是否按「境界/修为」语义使用。"""
    if not term:
        return False
    end = start + len(term)
    after = text[end:]
    before = text[:start]

    for phrase in CULTIVATION_TERM_FALSE_POSITIVE_PHRASES.get(term, ()):
        if _occurrence_inside_false_positive_phrase(text, start, len(term), phrase):
            return False

    for suf in CULTIVATION_REALM_USAGE_SUFFIXES:
        if after.startswith(suf):
            return True

    window = before[-10:]
    if any(prefix in window for prefix in CULTIVATION_REALM_USAGE_PREFIXES):
        return True

    prev_c = before[-1] if before else ""
    next_c = after[0] if after else ""
    boundary_chars = "，。！？；：、】【（）() \n|"
    boundary_before = not prev_c or prev_c in boundary_chars
    boundary_after = not next_c or next_c in boundary_chars
    if boundary_before and boundary_after:
        return True

    return False


def _scan_banned_cultivation_terms(text: str, banned: set[str]) -> set[str]:
    """传统修真境界禁词：按境界语境匹配，避免 炼化神火 等复合词误报。"""
    if not text or not banned:
        return set()
    hits: set[str] = set()
    for term in banned:
        pos = 0
        while pos < len(text):
            idx = text.find(term, pos)
            if idx == -1:
                break
            if _is_cultivation_realm_term_usage(text, idx, term):
                hits.add(term)
                break
            pos = idx + 1
    return hits


def detect_outline_terminology_issues(
    chapters: list[dict],
    *,
    power_systems,
    genre: str = "",
) -> list[dict]:
    """
    扫描章节大纲文本，识别两类术语脱轨：
      1. 项目 PowerSystem 之外的传统修真术语（critical）。
      2. 玄幻题材下的现代/科幻词汇（critical）。
    """
    if power_systems is None:
        return []
    whitelist = collect_power_system_whitelist(power_systems)
    cultivation_pool = {term for term in TRADITIONAL_CULTIVATION_BLACKLIST if term not in whitelist}
    is_xuanhuan = _is_xuanhuan_like_genre(genre)
    modern_pool = MODERN_BLACKLIST_FOR_XUANHUAN if is_xuanhuan else set()

    if not cultivation_pool and not modern_pool:
        return []

    issues: list[dict] = []
    whitelist_label = "、".join(sorted(whitelist)) if whitelist else "（项目尚未配置力量体系）"

    for chapter in chapters:
        number = chapter.get("number")
        if not isinstance(number, int):
            continue
        text_blob = " | ".join(
            str(chapter.get(field, ""))
            for field in ("title", "opening_hook", "core_event", "character_change", "foreshadow", "end_hook")
        )
        cultivation_hits = sorted(_scan_banned_cultivation_terms(text_blob, cultivation_pool))
        modern_hits = sorted(_scan_banned_terms(text_blob, modern_pool))

        if cultivation_hits:
            issues.append({
                "severity": "critical", "type": "continuity",
                "chapter_numbers": [number],
                "description": (
                    f"第{number}章使用了项目力量体系外的修真术语：{'、'.join(cultivation_hits)}。"
                    f"项目实际境界白名单：{whitelist_label[:160]}。"
                    "需替换为项目自定义境界，否则破坏世界观一致性，连锁影响后续卷设定。"
                ),
                "suggested_patch": {"chapter_number": number, "field": "core_event", "replacement": ""},
            })
        if modern_hits:
            issues.append({
                "severity": "critical", "type": "continuity",
                "chapter_numbers": [number],
                "description": (
                    f"第{number}章在玄幻/仙侠题材下出现现代/科幻词汇：{'、'.join(modern_hits)}。"
                    "需改写为东方玄幻意象（阵法中枢、古禁制、神纹、天机枢纽、血脉禁室等）。"
                ),
                "suggested_patch": {"chapter_number": number, "field": "core_event", "replacement": ""},
            })
    return issues
