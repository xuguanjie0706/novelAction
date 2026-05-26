"""
境界白名单、术语扫描、人物境界归因与成长里程碑时间轴。

拆分结构：
  - realm_whitelist.py: 白名单构建 + 术语禁词扫描
  - realm_attribution.py: 人物境界归因判定
  - 本文件: 时间轴构建 / 合并逻辑 + re-export 公共 API
"""
from __future__ import annotations

from typing import Any

# ── re-export：保持外部 import 路径不变 ──────────────────────────
from app.routers.outline.helpers.realm_whitelist import (  # noqa: F401
    collect_power_system_whitelist as _collect_power_system_whitelist,
    build_realm_rank_map as _build_realm_rank_map,
    detect_outline_terminology_issues as _detect_outline_terminology_issues,
    _scan_banned_terms,
)
from app.routers.outline.helpers.realm_attribution import (  # noqa: F401
    chapter_growth_scan_text as _chapter_growth_scan_text,
    character_realm_attributed as _character_realm_attributed,
    extract_character_realm_rank as _extract_character_realm_rank,
    parse_chapter_number_label as _parse_chapter_number_label,
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


def _protagonist_realm_attributed(
    text: str, realm_name: str, protagonist_names: list[str], *, max_span: int = 56,
) -> bool:
    return _character_realm_attributed(
        text, realm_name, protagonist_names, max_span=max_span, role_label="protagonist",
    )


def _extract_protagonist_realm_rank(
    chapter: dict, name_to_rank: dict[str, int], *, protagonist_names: list[str] | None = None,
) -> int | None:
    return _extract_character_realm_rank(
        chapter, name_to_rank, character_names=protagonist_names, role_label="protagonist",
    )


def _extract_max_realm_from_chapters(
    chapters: list[dict], name_to_rank: dict[str, int], protagonist_names: list[str] | None = None,
) -> tuple[int | None, str | None]:
    """从已生成章节列表中扫描 character_change，提取主角出现过的最高境界 rank 及对应名称。"""
    max_rank: int | None = None
    max_realm: str | None = None
    rank_to_name = {v: k for k, v in name_to_rank.items()}
    for chapter in chapters:
        rank = _extract_protagonist_realm_rank(chapter, name_to_rank, protagonist_names=protagonist_names)
        if rank is not None and (max_rank is None or rank > max_rank):
            max_rank = rank
            max_realm = rank_to_name.get(rank, str(rank))
    return max_rank, max_realm


def _realm_display_name_for_rank(rank: int, name_to_rank: dict[str, int]) -> str:
    """同一 rank 可能对应全名与简写，优先展示带「境」的较长名称。"""
    candidates = [n for n, r in name_to_rank.items() if r == rank]
    if not candidates:
        return f"rank{rank}"
    with_jing = [n for n in candidates if isinstance(n, str) and n.endswith("境")]
    pool = with_jing if with_jing else candidates
    return max(pool, key=len)


# 与 ai.chapter_debrief 写入保持一致
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
        if not isinstance(name, str) or len(name) < 2:
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
        events.append({
            "chapter_number": int(m["chapter_number"]),
            "chapter_title": str(m.get("chapter_title") or ""),
            "realm_name": str(m.get("realm_name") or ""),
            "realm_rank": int(m["realm_rank"]),
            "character_change": str(m.get("character_change") or ""),
            "source": "outline",
        })
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
        if not disp and name_to_rank and rr > 0:
            disp = _realm_display_name_for_rank(rr, name_to_rank)
        elif not disp and rr > 0:
            disp = f"rank{rr}"
        events.append({
            "chapter_number": ch,
            "chapter_title": str(d.get("chapter_title") or "")[:400],
            "realm_name": disp or f"rank{rr}",
            "realm_rank": rr,
            "character_change": "正文复盘 character_updates",
            "source": "debrief",
        })

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
    prev_merged_name = ""
    merged: list[dict[str, Any]] = []
    for ch, best, r in per_chapter:
        nm = str(best.get("realm_name") or "").strip()
        src = str(best.get("source") or "outline")
        if name_to_rank:
            rank_increased = r > running
            name_progression = (
                src in ("debrief", "changelog")
                and bool(nm) and nm != prev_merged_name and r >= running
            )
            if not (rank_increased or name_progression):
                continue
            if rank_increased:
                running = r
            if nm:
                prev_merged_name = nm
            merged.append({
                "chapter_number": ch,
                "chapter_title": best.get("chapter_title") or "",
                "realm_name": nm or _realm_display_name_for_rank(r, name_to_rank),
                "realm_rank": r,
                "character_change": str(best.get("character_change") or ""),
                "source": src,
            })
        else:
            if r > running:
                running = r
                merged.append({
                    "chapter_number": ch,
                    "chapter_title": best.get("chapter_title") or "",
                    "realm_name": nm or f"rank{r}",
                    "realm_rank": r,
                    "character_change": str(best.get("character_change") or ""),
                    "source": str(best.get("source") or "outline"),
                })
            elif nm and nm != prev_merged_name:
                prev_merged_name = nm
                merged.append({
                    "chapter_number": ch,
                    "chapter_title": best.get("chapter_title") or "",
                    "realm_name": nm,
                    "realm_rank": 0,
                    "character_change": str(best.get("character_change") or ""),
                    "source": str(best.get("source") or "outline"),
                })

    return merged


def build_character_realm_timeline(
    chapter_contexts: list[dict], power_systems, *,
    character_names: list[str] | None = None, role_label: str | None = None,
) -> dict[str, Any]:
    """从章节计划的人物变化 + 实力里程碑聚合该人物境界「创新高」节点。"""
    name_to_rank, _, _ = _build_realm_rank_map(power_systems)
    if not name_to_rank:
        return {"has_realm_whitelist": False, "anchored": bool(character_names),
                "chapter_plans_scanned": 0, "milestones": []}
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
            ch, name_to_rank, character_names=use_names, role_label=role_label,
        )
        if rank is None or rank <= running:
            continue
        running = rank
        realm_label = _realm_display_name_for_rank(rank, name_to_rank)
        cc = _chapter_growth_scan_text(ch)
        milestones.append({
            "chapter_number": int(ch["number"]),
            "chapter_title": str(ch.get("title") or ""),
            "realm_name": realm_label, "realm_rank": rank,
            "character_change": cc[:400],
        })

    return {"has_realm_whitelist": True, "anchored": bool(anchors),
            "chapter_plans_scanned": len(sorted_chapters), "milestones": milestones}


def build_protagonist_realm_timeline(
    chapter_contexts: list[dict], power_systems, *,
    protagonist_names: list[str] | None = None,
) -> dict[str, Any]:
    return build_character_realm_timeline(
        chapter_contexts, power_systems,
        character_names=protagonist_names, role_label="protagonist",
    )


def milestones_from_changelog(
    change_logs: list[Any], name_to_rank: dict[str, int],
) -> list[dict[str, Any]]:
    """从 CharacterChangeLog 的 current_realm 变更提取里程碑。"""
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
            rows.append({
                "chapter_number": ch_num,
                "chapter_title": str(getattr(log, "chapter_title", None) or "")[:400],
                "realm_name": after,
                "realm_rank": rr if rr is not None else 0,
                "character_change": str(getattr(log, "summary", None) or "变更记录"),
                "source": "changelog",
            })
            break
    return rows


def build_character_growth_timeline(
    chapter_contexts: list[dict], power_systems, character, *,
    change_logs: list[Any] | None = None,
) -> dict[str, Any]:
    """合并大纲、复盘快照与变更记录，返回单人物成长时间轴 payload。"""
    anchor_names = _collect_character_anchor_names(character)
    role_label = getattr(character, "role", None)
    built = build_character_realm_timeline(
        chapter_contexts, power_systems,
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
        built["milestones"], debrief_rows, name_to_rank,
    )
    if changelog_rows:
        merged = merge_outline_and_debrief_realm_milestones(
            merged_outline_debrief, changelog_rows, name_to_rank,
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
