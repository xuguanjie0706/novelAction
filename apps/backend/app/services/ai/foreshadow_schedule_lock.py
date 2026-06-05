"""
伏笔日程锁定表：由 core_mysteries + opening_contract + 本章章纲确定性生成。

与 chapter_lock_table（上章→本章不倒带）互补；第 1 章起即可生效。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Chapter, OutlineNode, Project
from app.services.bootstrap.foreshadow_ops import extract_lay_names, normalize_op
from app.services.bootstrap.foreshadow_sync import _RE_LAY
from app.utils.chapter_numbering import display_chapter_number

_RE_KEYWORD = re.compile(r"[\u4e00-\u9fff]{2,}")

# 正文提前埋设质检：短语最短匹配长度（过滤 2～3 字误杀）
_MIN_AUDIT_PHRASE_LEN = 4


def _extract_keywords(text: str) -> list[str]:
    """从中文文本提取可用于匹配的连续汉字片段。"""
    if not text:
        return []
    parts = _RE_KEYWORD.findall(text)
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:12]


def _keywords_overlap(a: str, b_keywords: list[str]) -> bool:
    a = (a or "").strip()
    if not a:
        return False
    for kw in b_keywords:
        if not kw:
            continue
        if kw in a or a in kw:
            return True
    return False


def planned_lay_chapter(foreshadow: Any, mysteries_by_name: dict[str, dict]) -> int | None:
    """解析伏笔的计划埋设章（优先 core_mysteries，其次 extra / laid_chapter_number）。"""
    extra = foreshadow.extra if isinstance(getattr(foreshadow, "extra", None), dict) else {}
    if extra.get("planned_lay_chapter"):
        try:
            return int(extra["planned_lay_chapter"])
        except (TypeError, ValueError):
            pass
    mn = (extra.get("mystery_name") or "").strip()
    title = (getattr(foreshadow, "title", None) or "").strip()
    for key in (mn, title):
        if key and key in mysteries_by_name:
            try:
                return int(mysteries_by_name[key].get("lay_chapter") or 0) or None
            except (TypeError, ValueError):
                pass
    if extra.get("is_core_mystery") and getattr(foreshadow, "laid_chapter_number", None):
        return foreshadow.laid_chapter_number
    laid = getattr(foreshadow, "laid_chapter_number", None)
    if laid and not extra.get("source_outline_node_id"):
        return laid
    return laid


def format_foreshadow_ledger_line(foreshadow: Any, chapter_number: int, mysteries_by_name: dict[str, dict]) -> str:
    """写前预警 / 门控路径统一的伏笔台账行格式。"""
    code = getattr(foreshadow, "code", None) or "—"
    title = (getattr(foreshadow, "title", None) or "").strip()
    planned_lay = planned_lay_chapter(foreshadow, mysteries_by_name)
    resolve = getattr(foreshadow, "planned_resolve_chapter", None)
    desc = (getattr(foreshadow, "description", None) or "")[:100]

    overdue = ""
    if resolve and chapter_number > 0 and resolve <= chapter_number:
        overdue = "【⚠️已逾期】"
    early = ""
    if planned_lay and chapter_number > 0 and planned_lay > chapter_number:
        early = "【⏳未到埋设章】"

    lay_part = f"计划埋第{planned_lay}章" if planned_lay else "计划埋=未定"
    resolve_part = f"预计回收第{resolve}章" if resolve else "预计回收=未定"
    return f"{overdue}{early}{code} {title} | {lay_part} | {resolve_part} | {desc}"


def build_foreshadow_ledger(
    foreshadows: list[Any],
    chapter_number: int,
    mysteries: list[dict],
) -> str:
    """批量格式化伏笔台账文本块。"""
    by_name = {
        (m.get("name") or "").strip(): m
        for m in mysteries
        if isinstance(m, dict) and (m.get("name") or "").strip()
    }
    lines = [
        format_foreshadow_ledger_line(f, chapter_number, by_name)
        for f in foreshadows
    ]
    return "\n".join(lines)


def _opening_teases(opening: dict, chapter_number: int) -> list[dict[str, Any]]:
    """开局承诺中允许本章做的「预告/钩子」（非完整埋设）。"""
    if not opening or chapter_number < 1 or chapter_number > 10:
        return []
    mapping: list[tuple[int, str, str]] = [
        (1, "chapter1_hook", "第1章末钩子"),
        (3, "chapter3_payoff", "第3章小爽点"),
        (5, "chapter5_foreshadow", "第5章长线伏笔"),
        (10, "chapter10_subscribe_reason", "第10章订阅钩"),
    ]
    teases: list[dict[str, Any]] = []
    for ch, key, label in mapping:
        if ch != chapter_number:
            continue
        val = (opening.get(key) or "").strip()
        if val:
            teases.append({
                "label": label,
                "detail": val[:280],
                "keywords": _extract_keywords(val),
            })
    return teases


def _detect_outline_early_lay_from_ops(
    ops: list[dict[str, Any]],
    forbidden_early: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """章纲 foreshadow_ops 是否含 lay 但日程表禁止提前埋设。"""
    if not ops or not forbidden_early:
        return []
    conflicts: list[dict[str, str]] = []
    for lay_text in extract_lay_names(ops):
        for item in forbidden_early:
            if _keywords_overlap(lay_text, item.get("keywords") or []):
                conflicts.append({
                    "field": "foreshadow_ops",
                    "outline_text": lay_text[:200],
                    "reason": item.get("reason", ""),
                })
                break
    return conflicts


def _detect_outline_early_lay(
    foreshadow_raw: str,
    forbidden_early: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """legacy：章纲 foreshadow 文本是否含「埋[…]」但日程表禁止提前埋设。"""
    if not foreshadow_raw.strip() or not forbidden_early:
        return []
    conflicts: list[dict[str, str]] = []
    for m in _RE_LAY.finditer(foreshadow_raw):
        lay_text = (m.group(1).split("|")[0] if "|" in m.group(1) else m.group(1)).strip()
        if not lay_text:
            continue
        for item in forbidden_early:
            if _keywords_overlap(lay_text, item.get("keywords") or []):
                conflicts.append({
                    "field": "foreshadow",
                    "outline_text": lay_text[:200],
                    "reason": item.get("reason", ""),
                })
                break
    return conflicts


def build_foreshadow_schedule_lock(
    db: Session,
    project_id: str,
    chapter: Chapter,
    outline_node: OutlineNode | None = None,
) -> dict[str, Any]:
    """
    生成伏笔日程锁定表（无 LLM）。

    Returns:
        forbidden_early_plants, allowed_this_chapter, opening_teases,
        outline_conflicts, prompt_block, current_chapter_number
    """
    ch_no = display_chapter_number(chapter.title, chapter.sort_order)
    project = db.query(Project).filter(Project.id == project_id).first()
    extra = project.extra if project and isinstance(project.extra, dict) else {}
    mysteries = [m for m in (extra.get("core_mysteries") or []) if isinstance(m, dict)]
    opening = extra.get("opening_contract") if isinstance(extra.get("opening_contract"), dict) else {}

    if outline_node is None and chapter.outline_node_id:
        outline_node = db.query(OutlineNode).filter(OutlineNode.id == chapter.outline_node_id).first()

    forbidden_early: list[dict[str, Any]] = []
    allowed_this_chapter: list[dict[str, Any]] = []

    for m in mysteries:
        name = (m.get("name") or "").strip()
        if not name:
            continue
        try:
            lay = int(m.get("lay_chapter") or 0)
        except (TypeError, ValueError):
            lay = 0
        keywords = _extract_keywords(name) + _extract_keywords(m.get("lay_method") or "")
        heat_chapters = m.get("heat_chapters") or []
        if not isinstance(heat_chapters, list):
            heat_chapters = []

        if lay and lay > ch_no:
            lay_method = (m.get("lay_method") or "").strip()
            forbidden_early.append({
                "name": name,
                "planned_lay_chapter": lay,
                "keywords": keywords,
                "lay_method": lay_method,
                "audit_phrases": _build_audit_phrases(
                    name, keywords, lay_method,
                ),
                "reason": (
                    f"核心谜题「{name}」计划第{lay}章才正式埋下，"
                    f"第{ch_no}章禁止完整埋设（不得点名/描写 lay_method 中的关键细节）。"
                ),
            })
        elif lay == ch_no:
            allowed_this_chapter.append({
                "name": name,
                "op": "lay",
                "detail": (m.get("lay_method") or "")[:200],
            })

        for hc in heat_chapters:
            try:
                hc_int = int(hc)
            except (TypeError, ValueError):
                continue
            if hc_int == ch_no:
                allowed_this_chapter.append({
                    "name": name,
                    "op": "heat",
                    "detail": "",
                })

    opening_teases = _opening_teases(opening, ch_no)
    outline_conflicts: list[dict[str, str]] = []
    if outline_node:
        extra = outline_node.extra if isinstance(outline_node.extra, dict) else {}
        raw_ops = extra.get("foreshadow_ops")
        if isinstance(raw_ops, list) and raw_ops:
            normalized = [o for o in (normalize_op(x) for x in raw_ops) if o]
            outline_conflicts = _detect_outline_early_lay_from_ops(
                normalized, forbidden_early,
            )
        else:
            foreshadow_raw = (extra.get("foreshadow") or "").strip()
            outline_conflicts = _detect_outline_early_lay(
                foreshadow_raw, forbidden_early,
            )

    lock: dict[str, Any] = {
        "current_chapter_number": ch_no,
        "forbidden_early_plants": forbidden_early,
        "allowed_this_chapter": allowed_this_chapter,
        "opening_teases": opening_teases,
        "outline_conflicts": outline_conflicts,
        "has_schedule": bool(forbidden_early or allowed_this_chapter or opening_teases),
    }
    lock["prompt_block"] = format_foreshadow_schedule_prompt_block(lock)
    return lock


def format_foreshadow_schedule_prompt_block(lock: dict[str, Any]) -> str:
    """格式化为注入 pre_write_warning 的文本块。"""
    if not lock.get("has_schedule"):
        return "（无核心谜题日程或未进入开局窗口）"

    ch = lock.get("current_chapter_number")
    lines = [
        f"▍伏笔日程锁定表（第{ch}章，程序生成，优先级高于章纲 foreshadow 字面与本章 must_events）",
    ]

    teases = lock.get("opening_teases") or []
    if teases:
        lines.append("▍开局承诺允许本章的预告（非完整埋设）")
        for t in teases:
            lines.append(f"  · {t.get('label')}：{t.get('detail', '')}")

    allowed = lock.get("allowed_this_chapter") or []
    if allowed:
        lines.append("▍本章应处理的伏笔日程")
        for a in allowed:
            op = "埋设" if a.get("op") == "lay" else "加热"
            detail = f" — {a['detail']}" if a.get("detail") else ""
            lines.append(f"  · [{op}] {a.get('name', '')}{detail}")

    forbidden = lock.get("forbidden_early_plants") or []
    if forbidden:
        lines.append("▍禁止提前完整埋设（违者视为伏笔违约）")
        for f in forbidden:
            lines.append(f"  ⛔ 第{f.get('planned_lay_chapter')}章才埋：{f.get('name')} — {f.get('reason', '')[:120]}")

    conflicts = lock.get("outline_conflicts") or []
    if conflicts:
        lines.append("▍章纲伏笔冲突（须改章纲后再写）")
        for c in conflicts:
            lines.append(f"  ⚠️ [{c.get('field')}] {c.get('reason', '')}")

    return "\n".join(lines)


def merge_foreshadow_schedule_into_warn_result(warn_result: dict, lock: dict[str, Any]) -> dict:
    """将伏笔日程表并入预警结果，并把章纲冲突提升为 risks。"""
    out = dict(warn_result)
    out["foreshadow_schedule_lock"] = {
        "has_schedule": lock.get("has_schedule", False),
        "current_chapter_number": lock.get("current_chapter_number"),
        "forbidden_early_plants": lock.get("forbidden_early_plants") or [],
        "allowed_this_chapter": lock.get("allowed_this_chapter") or [],
        "opening_teases": lock.get("opening_teases") or [],
        "outline_conflicts": lock.get("outline_conflicts") or [],
    }
    risks = list(out.get("risks") or [])
    existing_desc = {str(r.get("description", ""))[:120] for r in risks if isinstance(r, dict)}
    for c in lock.get("outline_conflicts") or []:
        desc = c.get("reason", "")
        if not desc or desc[:120] in existing_desc:
            continue
        risks.insert(
            0,
            {
                "type": "foreshadow",
                "severity": "critical",
                "description": desc,
                "suggested_fix": "修改本章章纲 foreshadow 字段，将「埋」改为「加热」或删除，待计划章再埋设。",
            },
        )
        existing_desc.add(desc[:120])

    for item in lock.get("forbidden_early_plants") or []:
        name = item.get("name", "")
        lay = item.get("planned_lay_chapter")
        if not name or not lay:
            continue
        desc = (
            f"伏笔日程：「{name}」计划第{lay}章埋设，"
            f"第{lock.get('current_chapter_number')}章不得完整写出。"
        )
        if desc[:120] in existing_desc:
            continue
        risks.append({
            "type": "foreshadow",
            "severity": "high",
            "description": desc,
            "suggested_fix": "正文仅可留模糊暗示；完整细节留到计划章。",
        })
        existing_desc.add(desc[:120])

    out["risks"] = risks[:18]
    out["risk_count"] = len(out["risks"])
    if any(r.get("severity") in ("high", "critical") for r in out["risks"] if isinstance(r, dict)):
        out["ok"] = False
    return out


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").replace("&nbsp;", " ")


def _build_audit_phrases(
    name: str,
    keywords: list[str] | None,
    lay_method: str = "",
) -> list[str]:
    """
    正文质检触发短语：仅保留 ≥4 字片段，按长度降序（优先最长匹配，降低误杀）。
    """
    phrases: set[str] = set()
    n = (name or "").strip()
    if len(n) >= 3:
        phrases.add(n)
    for kw in keywords or []:
        k = (kw or "").strip()
        if len(k) >= _MIN_AUDIT_PHRASE_LEN:
            phrases.add(k)
    for kw in _extract_keywords(lay_method or ""):
        if len(kw) >= _MIN_AUDIT_PHRASE_LEN:
            phrases.add(kw)
    ordered = sorted(phrases, key=len, reverse=True)
    if n and n in ordered:
        ordered.remove(n)
        return [n, *ordered]
    return ordered


def audit_early_foreshadow_plants(
    chapter_text: str,
    lock: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    确定性扫描正文是否提前写出「禁止完整埋设」伏笔的关键词（门控质检用）。

    Args:
        chapter_text: 章节正文（可含 HTML）。
        lock: build_foreshadow_schedule_lock 的返回值。

    Returns:
        违约列表，每项含 name / planned_lay_chapter / matched_keyword / description。
    """
    forbidden = lock.get("forbidden_early_plants") or []
    plain = _strip_html(chapter_text).strip()
    if not forbidden or not plain:
        return []

    violations: list[dict[str, Any]] = []
    for item in forbidden:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        lay = item.get("planned_lay_chapter")
        keywords = list(item.get("keywords") or [])
        phrases = item.get("audit_phrases") or _build_audit_phrases(
            name,
            keywords,
            (item.get("lay_method") or ""),
        )
        matched_kw = ""
        for phrase in phrases:
            if phrase and phrase in plain:
                matched_kw = phrase
                break
        if not matched_kw:
            continue
        violations.append({
            "name": name,
            "planned_lay_chapter": lay,
            "matched_keyword": matched_kw,
            "severity": "high",
            "description": (
                f"伏笔日程违约：「{name}」计划第{lay}章才完整埋设，"
                f"正文出现关键词「{matched_kw}」"
            ),
        })
    return violations


def merge_early_plant_audit_into_qc_result(
    qc_result: dict,
    violations: list[dict[str, Any]],
) -> dict:
    """将提前埋设违约并入质检结果，压低总分并写入 issues / suggestions。"""
    if not violations:
        return qc_result

    out = dict(qc_result)
    out["foreshadow_early_plant_violations"] = violations

    issues = list(out.get("issues") or [])
    existing = {str(i.get("description", ""))[:80] for i in issues if isinstance(i, dict)}
    for v in violations:
        desc = v.get("description", "")
        if desc[:80] in existing:
            continue
        issues.append({
            "type": "foreshadow",
            "severity": v.get("severity", "high"),
            "description": desc,
        })
        existing.add(desc[:80])
    out["issues"] = issues

    suggestions = list(out.get("suggestions") or [])
    for v in violations[:4]:
        kw = v.get("matched_keyword", "")
        lay = v.get("planned_lay_chapter", "?")
        name = v.get("name", "")
        tip = (
            f"伏笔日程：删除或模糊化「{kw}」相关描写（「{name}」完整埋设留到第{lay}章）"
        )
        if tip not in suggestions:
            suggestions.insert(0, tip)
    out["suggestions"] = suggestions[:12]

    overall = float(out.get("overall_score") or 10)
    cap = max(3.0, 5.5 - 0.5 * (len(violations) - 1))
    out["overall_score"] = min(overall, cap)

    dims = dict(out.get("dimensions") or {})
    plot = dict(dims.get("plot") or dims.get("outline_alignment") or {})
    if plot:
        plot_score = float(plot.get("score") or 10)
        plot["score"] = min(plot_score, cap)
        plot["comment"] = (
            (plot.get("comment") or "").strip()
            + f"；伏笔日程违约×{len(violations)}"
        ).strip("；")
        key = "plot" if "plot" in dims else "outline_alignment"
        dims[key] = plot
        out["dimensions"] = dims

    return out
