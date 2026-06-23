"""
跨章「认知边界」台账：谁已知道哪些设定专名。

落库：``Project.extra.narrative_knowledge``（复盘提交时由 chapter_index 字段合并更新）。
写章：``draft_continuity_bridge`` 读取并生成「未公开专名禁止旁白直写」硬约束。
"""

from __future__ import annotations

from typing import Any

from app.models import Project

NK_KEY = "narrative_knowledge"
_MAX_LOCKED_BEATS = 40
_MAX_TERMS = 32


def get_narrative_knowledge(project: Project) -> dict[str, Any]:
    extra = project.extra if isinstance(project.extra, dict) else {}
    nk = extra.get(NK_KEY)
    return dict(nk) if isinstance(nk, dict) else {}


def collect_golden_finger_terms(project: Project) -> list[str]:
    """Bootstrap 金手指规划中的专名（默认视为「未公开」，直到复盘写入台账）。"""
    gf = (project.extra or {}).get("golden_finger") if isinstance(project.extra, dict) else {}
    if not isinstance(gf, dict):
        return []
    terms: list[str] = []
    for key in ("finger_name", "finger_type"):
        raw = (gf.get(key) or "").strip()
        if not raw:
            continue
        terms.append(raw)
        if "·" in raw:
            terms.append(raw.split("·", 1)[0].strip())
        if "（" in raw:
            terms.append(raw.split("（", 1)[0].strip())
    out: list[str] = []
    seen: set[str] = set()
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _norm_terms(raw: list | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        t = (item if isinstance(item, str) else str(item)).strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:_MAX_TERMS]


def _fmt_event(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return (
            (item.get("beat") or item.get("event") or item.get("description") or "")
        ).strip()
    return str(item).strip() if item else ""


def merge_narrative_knowledge_from_debrief(
    project: Project,
    *,
    chapter_number: int,
    chapter_id: str | None = None,
    in_world_named_terms: list | None = None,
    protagonist_known_terms: list | None = None,
    core_events: list | None = None,
) -> bool:
    """
    复盘落库后合并认知台账与已锁定情节节拍。

    Returns:
        是否修改了 ``project.extra``。
    """
    nk = get_narrative_knowledge(project)
    term_events = [e for e in (nk.get("term_events") or []) if isinstance(e, dict)]
    if not term_events and (nk.get("public_terms") or nk.get("protagonist_terms")):
        term_events.append({
            "chapter": 0,
            "public_terms": _norm_terms(nk.get("public_terms")),
            "protagonist_terms": _norm_terms(nk.get("protagonist_terms")),
            "source": "legacy_baseline",
        })
    term_events = [
        e for e in term_events
        if not (
            (chapter_id and str(e.get("chapter_id") or "") == str(chapter_id))
            or (not chapter_id and int(e.get("chapter") or -1) == chapter_number)
        )
    ]
    term_events.append({
        "chapter": chapter_number,
        "chapter_id": chapter_id,
        "public_terms": _norm_terms(in_world_named_terms),
        "protagonist_terms": _norm_terms(protagonist_known_terms),
    })
    term_events = term_events[-_MAX_LOCKED_BEATS:]

    public: set[str] = set()
    prot: set[str] = set()
    for event in term_events:
        public.update(_norm_terms(event.get("public_terms")))
        event_prot = _norm_terms(event.get("protagonist_terms"))
        prot.update(event_prot)
        public.update(event_prot)

    beats: list[dict] = list(nk.get("locked_plot_beats") or [])
    existing_text = {b.get("beat") for b in beats if isinstance(b, dict)}
    for ev in core_events or []:
        text = _fmt_event(ev)
        if not text or text in existing_text:
            continue
        beats.append({"chapter": chapter_number, "chapter_id": chapter_id, "beat": text[:240]})
        existing_text.add(text)

    beats = beats[-_MAX_LOCKED_BEATS:]
    new_nk = {
        "public_terms": sorted(public)[:_MAX_TERMS],
        "protagonist_terms": sorted(prot)[:_MAX_TERMS],
        "term_events": term_events,
        "locked_plot_beats": beats,
    }
    extra = dict(project.extra) if isinstance(project.extra, dict) else {}
    if extra.get(NK_KEY) == new_nk:
        return False
    extra[NK_KEY] = new_nk
    project.extra = extra
    return True


def remove_chapter_narrative_knowledge(
    project: Project, *, chapter_number: int, chapter_id: str | None = None,
) -> bool:
    """撤销指定章节写入的认知专名与锁定情节，并由剩余事件重建集合。"""
    nk = get_narrative_knowledge(project)
    old_events = [e for e in (nk.get("term_events") or []) if isinstance(e, dict)]
    def _belongs_to_chapter(row: dict) -> bool:
        if chapter_id and row.get("chapter_id"):
            return str(row.get("chapter_id")) == str(chapter_id)
        return int(row.get("chapter") or -1) == chapter_number

    events = [e for e in old_events if not _belongs_to_chapter(e)]
    old_beats = [b for b in (nk.get("locked_plot_beats") or []) if isinstance(b, dict)]
    beats = [b for b in old_beats if not _belongs_to_chapter(b)]
    if len(events) == len(old_events) and len(beats) == len(old_beats):
        return False

    public: set[str] = set()
    prot: set[str] = set()
    for event in events:
        public.update(_norm_terms(event.get("public_terms")))
        event_prot = _norm_terms(event.get("protagonist_terms"))
        prot.update(event_prot)
        public.update(event_prot)

    extra = dict(project.extra) if isinstance(project.extra, dict) else {}
    extra[NK_KEY] = {
        "public_terms": sorted(public)[:_MAX_TERMS],
        "protagonist_terms": sorted(prot)[:_MAX_TERMS],
        "term_events": events,
        "locked_plot_beats": beats,
    }
    project.extra = extra
    return True


def terms_hidden_from_narration(project: Project) -> list[str]:
    """规划中有、但尚未进入 public/protagonist 台账的专名。"""
    nk = get_narrative_knowledge(project)
    known = set(_norm_terms(nk.get("public_terms"))) | set(
        _norm_terms(nk.get("protagonist_terms"))
    )
    hidden: list[str] = []
    for t in collect_golden_finger_terms(project):
        if t not in known:
            hidden.append(t)
    return hidden[:12]


def build_knowledge_boundary_lines(project: Project) -> list[str]:
    """供写章 prompt 使用的认知边界说明行。"""
    nk = get_narrative_knowledge(project)
    public = _norm_terms(nk.get("public_terms"))
    prot = _norm_terms(nk.get("protagonist_terms"))
    hidden = terms_hidden_from_narration(project)

    lines: list[str] = [
        "▍认知边界（设定专名何时能写出来）",
        "· 在场角色未获知、未公认的信息，不得由旁白直接写出完整设定专名。",
        "· 未公开前：用「黑焰」「异火」「经脉异变」等景象描写；主角内心最多用「某种体质/古怪力量」。",
    ]
    if hidden:
        lines.append(
            "· 下列专名尚未进入公开/主角认知台账，本章旁白与对话禁止直呼："
            + "、".join(f"「{t}」" for t in hidden)
        )
    if public:
        lines.append("· 已公开（角色可当面讨论）：" + "、".join(public[:16]))
    if prot:
        lines.append(
            "· 主角已确认（仅 POV 内心/独白可用专名，他人仍按公开名单）："
            + "、".join(prot[:16])
        )
    if not hidden and not public and not prot:
        lines.append("· 尚无复盘台账时：金手指/体质全名默认视为未公开，禁止旁白科普式点名。")
    return lines
