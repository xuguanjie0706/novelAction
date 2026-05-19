"""境界白名单、术语扫描、人物境界归因与成长里程碑时间轴。"""
from __future__ import annotations

import re
from typing import Any

from app.services.xuanhuan_lexicon import (
    MODERN_BLACKLIST_FOR_XUANHUAN,
    is_xuanhuan_like_genre as _is_xuanhuan_like_genre,
)

from app.routers.outline.helpers.constants import (
    CULTIVATION_REALM_USAGE_PREFIXES,
    CULTIVATION_REALM_USAGE_SUFFIXES,
    CULTIVATION_TERM_FALSE_POSITIVE_PHRASES,
    PROTAGONIST_REALM_ATTRIBUTION_VERBS,
    TRADITIONAL_CULTIVATION_BLACKLIST,
)

def _collect_character_anchor_names(char) -> list[str]:
    """单人物姓名 + 别名，用于境界归因扫描（去重保序）。"""
    anchors: list[str] = []
    name = getattr(char, "name", None)
    if isinstance(name, str) and name.strip():
        anchors.append(name.strip())
    raw_aliases = getattr(char, "alias", None) or []
    if isinstance(raw_aliases, list):
        for a in raw_aliases:
            if isinstance(a, str) and a.strip():
                anchors.append(a.strip())
    return list(dict.fromkeys(anchors))


def _collect_protagonist_anchor_names(characters) -> list[str]:
    """主角姓名 + 别名，用于境界归因扫描（去重保序）。"""
    anchors: list[str] = []
    for char in characters or []:
        if getattr(char, "role", None) != "protagonist":
            continue
        anchors.extend(_collect_character_anchor_names(char))
    return list(dict.fromkeys(anchors))


def _chapter_growth_scan_text(chapter: dict) -> str:
    """合并章纲中可能承载人物/境界变化的字段（人物变化 + 实力里程碑）。"""
    parts = [
        str(chapter.get("character_change") or ""),
        str(chapter.get("power_milestone") or ""),
    ]
    return " | ".join(p for p in parts if p.strip())


def _parse_chapter_number_label(label: Any) -> int | None:
    """从「第15章」或纯数字章号解析整数。"""
    if label is None:
        return None
    if isinstance(label, int):
        return label if label > 0 else None
    s = str(label).strip()
    if not s:
        return None
    m = re.match(r"^\s*第\s*0*(\d+)", s)
    if m:
        return int(m.group(1))
    try:
        n = int(s)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _character_realm_attributed(
    text: str,
    realm_name: str,
    character_names: list[str],
    *,
    max_span: int = 56,
    role_label: str | None = None,
) -> bool:
    """
    判断 text 中的 realm_name 是否应计作「该人物修为描写」。
    要求：与任一姓名/别名（主角可额外匹配「主角」）同处短跨度内，且出现修为归因信号，
    避免「林烬遭遇灵王境强敌」把灵王境记成该人物境界。
    """
    anchors = [n for n in character_names if isinstance(n, str) and n.strip()]
    if not anchors:
        return True
    if role_label == "protagonist":
        anchors = list(dict.fromkeys([*anchors, "主角"]))
    else:
        anchors = list(dict.fromkeys(anchors))
    for pname in anchors:
        p_start = 0
        while True:
            p = text.find(pname, p_start)
            if p == -1:
                break
            r_start = 0
            while True:
                r = text.find(realm_name, r_start)
                if r == -1:
                    break
                lo = min(p, r)
                hi = max(p + len(pname), r + len(realm_name))
                if hi - lo > max_span:
                    r_start = r + 1
                    continue
                mid = text[lo:hi]
                if any(v in mid for v in PROTAGONIST_REALM_ATTRIBUTION_VERBS):
                    return True
                if f"以{realm_name}" in mid or f"从{realm_name}" in mid:
                    return True
                r_start = r + 1
            p_start = p + 1
    return False


def _protagonist_realm_attributed(
    text: str,
    realm_name: str,
    protagonist_names: list[str],
    *,
    max_span: int = 56,
) -> bool:
    return _character_realm_attributed(
        text, realm_name, protagonist_names, max_span=max_span, role_label="protagonist",
    )


def _extract_max_realm_from_chapters(
    chapters: list[dict],
    name_to_rank: dict[str, int],
    protagonist_names: list[str] | None = None,
) -> tuple[int | None, str | None]:
    """从已生成章节列表中扫描 character_change，提取主角出现过的最高境界 rank 及对应名称。"""
    max_rank: int | None = None
    max_realm: str | None = None
    rank_to_name = {v: k for k, v in name_to_rank.items()}
    for chapter in chapters:
        rank = _extract_protagonist_realm_rank(
            chapter, name_to_rank, protagonist_names=protagonist_names
        )
        if rank is not None and (max_rank is None or rank > max_rank):
            max_rank = rank
            max_realm = rank_to_name.get(rank, str(rank))
    return max_rank, max_realm
def _collect_power_system_whitelist(power_systems) -> set[str]:
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
            if level_name.endswith("境") and len(level_name) > 1:
                whitelist.add(level_name[:-1])
    return whitelist


def _build_realm_rank_map(power_systems) -> tuple[dict[str, int], int | None, int | None]:
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
                if level_name.endswith("境") and len(level_name) > 1:
                    bare = level_name[:-1]
                    if bare not in name_to_rank or rank > name_to_rank[bare]:
                        name_to_rank[bare] = rank
                if rank > max_rank:
                    max_rank = rank
        declared = getattr(system, "protagonist_end_rank", None)
        if isinstance(declared, int) and declared > 0:
            end_rank = max(end_rank or 0, declared)
    return name_to_rank, (max_rank or None), end_rank


def _scan_banned_terms(text: str, banned: set[str]) -> set[str]:
    """现代/科幻禁词等：保持子串匹配（词表项本身不易误报）。"""
    if not text:
        return set()
    return {term for term in banned if term and term in text}


def _occurrence_inside_false_positive_phrase(
    text: str,
    start: int,
    term_len: int,
    phrase: str,
) -> bool:
    pos = text.find(phrase)
    while pos != -1:
        if pos <= start and start + term_len <= pos + len(phrase):
            return True
        pos = text.find(phrase, pos + 1)
    return False


def _is_cultivation_realm_term_usage(text: str, start: int, term: str) -> bool:
    """
    判断 term 在 start 处是否按「境界/修为」语义使用，而非子串误命中（如 炼化神火）。
    """
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


def _detect_outline_terminology_issues(
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
    whitelist = _collect_power_system_whitelist(power_systems)
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
                "severity": "critical",
                "type": "continuity",
                "chapter_numbers": [number],
                "description": (
                    f"第{number}章使用了项目力量体系外的修真术语：{'、'.join(cultivation_hits)}。"
                    f"项目实际境界白名单：{whitelist_label[:160]}。"
                    "需替换为项目自定义境界，否则破坏世界观一致性，连锁影响后续卷设定。"
                ),
                "suggested_patch": {
                    "chapter_number": number,
                    "field": "core_event",
                    "replacement": "",
                },
            })
        if modern_hits:
            issues.append({
                "severity": "critical",
                "type": "continuity",
                "chapter_numbers": [number],
                "description": (
                    f"第{number}章在玄幻/仙侠题材下出现现代/科幻词汇：{'、'.join(modern_hits)}。"
                    "需改写为东方玄幻意象（阵法中枢、古禁制、神纹、天机枢纽、血脉禁室等）。"
                ),
                "suggested_patch": {
                    "chapter_number": number,
                    "field": "core_event",
                    "replacement": "",
                },
            })
    return issues


def _extract_character_realm_rank(
    chapter: dict,
    name_to_rank: dict[str, int],
    *,
    character_names: list[str] | None = None,
    role_label: str | None = None,
) -> int | None:
    """
    扫描章纲人物变化 + 实力里程碑，返回该章中计作「该人物修为」的境界最大 rank。

    当传入 character_names（非空）时，仅统计与姓名共现且带修为归因语境的境界名。
    未传或为空列表时：取文中白名单境界最大 rank（兼容无人物卡的质检）。
    """
    text = _chapter_growth_scan_text(chapter)
    if not text or not name_to_rank:
        return None
    use_attribution = bool(character_names)
    found_rank: int | None = None
    for realm_name, rank in name_to_rank.items():
        if not realm_name or realm_name not in text:
            continue
        if use_attribution and not _character_realm_attributed(
            text,
            realm_name,
            character_names or [],
            role_label=role_label,
        ):
            continue
        if found_rank is None or rank > found_rank:
            found_rank = rank
    return found_rank


def _extract_protagonist_realm_rank(
    chapter: dict,
    name_to_rank: dict[str, int],
    *,
    protagonist_names: list[str] | None = None,
) -> int | None:
    return _extract_character_realm_rank(
        chapter,
        name_to_rank,
        character_names=protagonist_names,
        role_label="protagonist",
    )


def _realm_display_name_for_rank(rank: int, name_to_rank: dict[str, int]) -> str:
    """同一 rank 可能对应全名与简写，优先展示带「境」的较长名称。"""
    candidates = [n for n, r in name_to_rank.items() if r == rank]
    if not candidates:
        return f"rank{rank}"
    with_jing = [n for n in candidates if isinstance(n, str) and n.endswith("境")]
    pool = with_jing if with_jing else candidates
    return max(pool, key=len)


# 与 ai.chapter_debrief 写入保持一致（正文复盘提交时追加主角境界快照）
DEBRIEF_REALM_MILESTONES_EXTRA_KEY = "debrief_realm_milestones"


def _rank_for_realm_label(label: str, name_to_rank: dict[str, int]) -> int | None:
    """从自由文本境界名解析 rank；优先精确匹配，其次命中子串的最长境界名。"""
    if not label or not name_to_rank:
        return None
    s = label.strip()
    if s in name_to_rank:
        return name_to_rank[s]
    best: int | None = None
    best_len = 0
    for name, r in name_to_rank.items():
        if not isinstance(name, str) or not name:
            continue
        if name in s and len(name) >= best_len:
            if best is None or r >= best:
                best = r
                best_len = len(name)
    return best


def merge_outline_and_debrief_realm_milestones(
    outline_milestones: list[dict[str, Any]],
    debrief_rows: list[dict[str, Any]],
    name_to_rank: dict[str, int],
) -> list[dict[str, Any]]:
    """
    合并大纲「人物变化」里程碑与正文复盘提交时记录的主角境界快照，
    按章取各源中最高 rank，再全书扫一遍只保留「创新高」节点。
    """
    events: list[dict[str, Any]] = []
    for m in outline_milestones:
        events.append(
            {
                "chapter_number": int(m["chapter_number"]),
                "chapter_title": str(m.get("chapter_title") or ""),
                "realm_name": str(m.get("realm_name") or ""),
                "realm_rank": int(m["realm_rank"]),
                "character_change": str(m.get("character_change") or ""),
                "source": "outline",
            }
        )
    for d in debrief_rows:
        if not isinstance(d, dict):
            continue
        ch = d.get("chapter_number")
        if not isinstance(ch, int):
            try:
                ch = int(ch)
            except (TypeError, ValueError):
                continue
        raw_name = str(d.get("realm_name") or "").strip()
        rr = d.get("realm_rank")
        if isinstance(rr, bool) or rr is None:
            resolved = _rank_for_realm_label(raw_name, name_to_rank) if name_to_rank else None
            rr = resolved if resolved is not None else 0
        else:
            try:
                rr = int(rr)
            except (TypeError, ValueError):
                rr = _rank_for_realm_label(raw_name, name_to_rank) or 0
        if rr <= 0 and not raw_name:
            continue
        if rr <= 0 and name_to_rank:
            resolved = _rank_for_realm_label(raw_name, name_to_rank)
            if resolved is not None:
                rr = resolved
        disp = raw_name
        if name_to_rank and rr > 0:
            disp = _realm_display_name_for_rank(rr, name_to_rank)
        elif not disp and rr > 0:
            disp = _realm_display_name_for_rank(rr, name_to_rank)
        events.append(
            {
                "chapter_number": ch,
                "chapter_title": str(d.get("chapter_title") or "")[:400],
                "realm_name": disp or raw_name or f"rank{rr}",
                "realm_rank": rr,
                "character_change": "正文复盘 character_updates",
                "source": "debrief",
            }
        )

    if not events:
        return []

    by_ch: dict[int, list[dict[str, Any]]] = {}
    for e in events:
        ch = int(e["chapter_number"])
        by_ch.setdefault(ch, []).append(e)

    per_chapter: list[tuple[int, dict[str, Any], int]] = []
    for ch in sorted(by_ch.keys()):
        group = by_ch[ch]
        best: dict[str, Any] | None = None
        best_rank = -1
        for e in group:
            r = int(e.get("realm_rank") or 0)
            if r > best_rank:
                best_rank = r
                best = dict(e)
            elif r == best_rank and best is not None:
                if e.get("source") == "debrief" and best.get("source") != "debrief":
                    best = dict(e)
        if best is not None:
            per_chapter.append((ch, best, best_rank))

    running = 0
    prev_debrief_name = ""
    merged: list[dict[str, Any]] = []
    for ch, best, r in per_chapter:
        nm = str(best.get("realm_name") or "").strip()
        if name_to_rank:
            if r <= running:
                continue
            running = r
            merged.append(
                {
                    "chapter_number": ch,
                    "chapter_title": best.get("chapter_title") or "",
                    "realm_name": nm or _realm_display_name_for_rank(r, name_to_rank),
                    "realm_rank": r,
                    "character_change": str(best.get("character_change") or ""),
                    "source": str(best.get("source") or "outline"),
                }
            )
        else:
            if r > running:
                running = r
                merged.append(
                    {
                        "chapter_number": ch,
                        "chapter_title": best.get("chapter_title") or "",
                        "realm_name": nm or f"rank{r}",
                        "realm_rank": r,
                        "character_change": str(best.get("character_change") or ""),
                        "source": str(best.get("source") or "outline"),
                    }
                )
            elif nm and nm != prev_debrief_name:
                prev_debrief_name = nm
                merged.append(
                    {
                        "chapter_number": ch,
                        "chapter_title": best.get("chapter_title") or "",
                        "realm_name": nm,
                        "realm_rank": 0,
                        "character_change": str(best.get("character_change") or ""),
                        "source": str(best.get("source") or "outline"),
                    }
                )

    return merged


def build_character_realm_timeline(
    chapter_contexts: list[dict],
    power_systems,
    *,
    character_names: list[str] | None = None,
    role_label: str | None = None,
) -> dict[str, Any]:
    """
    从章节计划的人物变化 + 实力里程碑聚合该人物境界「创新高」节点。
    数据源为已入库的大纲 chapter_plan；无力量体系 levels 时无法解析境界名。
    """
    name_to_rank, _, _ = _build_realm_rank_map(power_systems)
    if not name_to_rank:
        return {
            "has_realm_whitelist": False,
            "anchored": bool(character_names),
            "chapter_plans_scanned": 0,
            "milestones": [],
        }
    anchors = [n for n in (character_names or []) if isinstance(n, str) and n.strip()]
    use_names: list[str] | None = anchors if anchors else None

    sorted_chapters = sorted(
        (c for c in chapter_contexts if isinstance(c.get("number"), int)),
        key=lambda c: int(c["number"]),
    )
    running = 0
    milestones: list[dict[str, Any]] = []
    for ch in sorted_chapters:
        rank = _extract_character_realm_rank(
            ch,
            name_to_rank,
            character_names=use_names,
            role_label=role_label,
        )
        if rank is None or rank <= running:
            continue
        running = rank
        realm_label = _realm_display_name_for_rank(rank, name_to_rank)
        cc = _chapter_growth_scan_text(ch)
        milestones.append(
            {
                "chapter_number": int(ch["number"]),
                "chapter_title": str(ch.get("title") or ""),
                "realm_name": realm_label,
                "realm_rank": rank,
                "character_change": cc[:400],
            }
        )

    return {
        "has_realm_whitelist": True,
        "anchored": bool(anchors),
        "chapter_plans_scanned": len(sorted_chapters),
        "milestones": milestones,
    }


def build_protagonist_realm_timeline(
    chapter_contexts: list[dict],
    power_systems,
    *,
    protagonist_names: list[str] | None = None,
) -> dict[str, Any]:
    return build_character_realm_timeline(
        chapter_contexts,
        power_systems,
        character_names=protagonist_names,
        role_label="protagonist",
    )


def milestones_from_changelog(
    change_logs: list[Any],
    name_to_rank: dict[str, int],
) -> list[dict[str, Any]]:
    """从 CharacterChangeLog 的 current_realm 变更提取里程碑（补全历史复盘数据）。"""
    rows: list[dict[str, Any]] = []
    for log in change_logs or []:
        ch_num = _parse_chapter_number_label(getattr(log, "chapter_number", None))
        if ch_num is None:
            continue
        changes = getattr(log, "changes", None) or []
        if not isinstance(changes, list):
            continue
        for chg in changes:
            if not isinstance(chg, dict) or chg.get("field") != "current_realm":
                continue
            after = str(chg.get("after") or "").strip()
            if not after:
                continue
            rr = _rank_for_realm_label(after, name_to_rank) if name_to_rank else None
            rows.append(
                {
                    "chapter_number": ch_num,
                    "chapter_title": str(getattr(log, "chapter_title", None) or "")[:400],
                    "realm_name": after,
                    "realm_rank": rr if rr is not None else 0,
                    "character_change": str(getattr(log, "summary", None) or "变更记录"),
                    "source": "changelog",
                }
            )
            break
    return rows


def build_character_growth_timeline(
    chapter_contexts: list[dict],
    power_systems,
    character,
    *,
    change_logs: list[Any] | None = None,
) -> dict[str, Any]:
    """
    合并大纲、复盘快照与变更记录，返回单人物成长时间轴 payload。
    """
    anchor_names = _collect_character_anchor_names(character)
    role_label = getattr(character, "role", None)
    built = build_character_realm_timeline(
        chapter_contexts,
        power_systems,
        character_names=anchor_names or None,
        role_label=role_label if role_label == "protagonist" else None,
    )
    name_to_rank, _, _ = _build_realm_rank_map(power_systems)
    debrief_rows: list[Any] = []
    extra = getattr(character, "extra", None)
    if isinstance(extra, dict):
        raw_hist = extra.get(DEBRIEF_REALM_MILESTONES_EXTRA_KEY)
        if isinstance(raw_hist, list):
            debrief_rows = [x for x in raw_hist if isinstance(x, dict)]

    changelog_rows = milestones_from_changelog(change_logs or [], name_to_rank)
    merged_outline_debrief = merge_outline_and_debrief_realm_milestones(
        built["milestones"],
        debrief_rows,
        name_to_rank,
    )
    if changelog_rows:
        merged = merge_outline_and_debrief_realm_milestones(
            merged_outline_debrief,
            changelog_rows,
            name_to_rank,
        )
    else:
        merged = merged_outline_debrief

    return {
        "character_id": str(getattr(character, "id", "")),
        "character_display_name": getattr(character, "name", None),
        "character_anchor_names": anchor_names,
        "has_realm_whitelist": built["has_realm_whitelist"],
        "anchored": built["anchored"],
        "chapter_plans_scanned": built["chapter_plans_scanned"],
        "debrief_snapshots": len(debrief_rows),
        "changelog_entries": len(changelog_rows),
        "milestones": merged,
        "source": "outline+debrief+changelog",
    }
