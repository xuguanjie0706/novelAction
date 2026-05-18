"""全书故事时间线聚合：章序横轴 + 卷/故事线/势力/伏笔/承诺/境界等多泳道甘特条。"""
from __future__ import annotations

import re
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import (
    Chapter,
    Character,
    Faction,
    Foreshadow,
    OutlineNode,
    PowerSystem,
    Project,
    ReaderPromise,
    StoryLine,
)
from app.utils.chapter_numbering import display_chapter_number

from app.routers.outline.helpers.expand_context import (
    _chapter_plan_root_volume,
    _outline_node_to_chapter_context,
    _sort_chapter_plan_nodes,
)
from app.routers.outline.helpers.realm_timeline import (
    _collect_protagonist_anchor_names,
    build_protagonist_realm_timeline,
    merge_outline_and_debrief_realm_milestones,
)
from app.routers.outline.helpers_core import (
    DEBRIEF_REALM_MILESTONES_EXTRA_KEY,
    _build_realm_rank_map,
)

_CHAPTER_RANGE_RE = re.compile(
    r"第?\s*0*(\d+)\s*[-~～至到]\s*第?\s*0*(\d+)\s*章?",
)
_SINGLE_CHAPTER_RE = re.compile(r"第?\s*0*(\d+)\s*章")


def parse_chapter_range(text: Optional[str]) -> tuple[int, int] | None:
    """从「第1-30章」「1~50」等文本解析闭区间章号；失败返回 None。"""
    if not text or not isinstance(text, str):
        return None
    raw = text.strip()
    m = _CHAPTER_RANGE_RE.search(raw)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    m2 = _SINGLE_CHAPTER_RE.search(raw)
    if m2:
        n = int(m2.group(1))
        return (n, n)
    return None


def _chapter_num_from_title(title: str, sort_order: int | None) -> int:
    return display_chapter_number(title, sort_order)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _extend_max(max_ch: int, *values: Any) -> int:
    for v in values:
        if v is None:
            continue
        n = _safe_int(v, 0)
        if n > max_ch:
            max_ch = n
    return max_ch


def build_story_timeline(db: Session, project_id: uuid.UUID) -> dict[str, Any]:
    """
    聚合项目内可映射到章序横轴的结构化条带与节点。

    Returns:
        dict 含 max_chapter、lanes（泳道元数据）、bars（甘特条/点）。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"max_chapter": 1, "lanes": [], "bars": []}

    nodes = (
        db.query(OutlineNode)
        .filter(OutlineNode.project_id == project_id)
        .order_by(OutlineNode.sort_order, OutlineNode.created_at)
        .all()
    )
    id_map = {n.id: n for n in nodes}
    plan_nodes = _sort_chapter_plan_nodes(
        [n for n in nodes if getattr(n, "node_type", None) == "chapter_plan"]
    )
    plan_ctx = [_outline_node_to_chapter_context(n) for n in plan_nodes]
    plan_by_id = {n.id: ctx for n, ctx in zip(plan_nodes, plan_ctx)}

    chapters = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id, Chapter.deleted_at.is_(None))
        .order_by(Chapter.sort_order)
        .all()
    )

    max_chapter = 1
    for ctx in plan_ctx:
        max_chapter = _extend_max(max_chapter, ctx.get("number"))
    for ch in chapters:
        max_chapter = _extend_max(max_chapter, ch.sort_order + 1 if ch.sort_order is not None else 1)

    bars: list[dict[str, Any]] = []

    # ── 卷阶段泳道 ──
    volumes = [n for n in nodes if getattr(n, "node_type", None) == "volume"]
    volumes.sort(key=lambda v: (v.sort_order or 0, str(v.id)))
    for vol in volumes:
        child_nums: list[int] = []
        for pn in plan_nodes:
            root = _chapter_plan_root_volume(pn, id_map)
            if root and root.id == vol.id:
                child_nums.append(_safe_int(plan_by_id[pn.id].get("number"), 0))
        if not child_nums:
            continue
        start, end = min(child_nums), max(child_nums)
        max_chapter = _extend_max(max_chapter, end)
        phase = getattr(vol, "phase", None) or ""
        bars.append(
            {
                "id": f"volume:{vol.id}",
                "lane": "volume",
                "label": vol.title or "未命名卷",
                "start_chapter": start,
                "end_chapter": end,
                "status": phase or None,
                "detail": (vol.summary or "")[:120] or None,
            }
        )

    # ── 正文章节（每章一格）──
    for ch in chapters:
        num = _chapter_num_from_title(ch.title or "", ch.sort_order)
        max_chapter = _extend_max(max_chapter, num)
        bars.append(
            {
                "id": f"chapter:{ch.id}",
                "lane": "chapter",
                "label": ch.title or f"第{num}章",
                "start_chapter": num,
                "end_chapter": num,
                "status": ch.status,
                "detail": f"{ch.word_count or 0} 字",
            }
        )

    # ── 故事线 + key_beats ──
    storylines = (
        db.query(StoryLine)
        .filter(StoryLine.project_id == project_id)
        .order_by(StoryLine.sort_order)
        .all()
    )
    for sl in storylines:
        start = sl.start_chapter
        end = sl.end_chapter or sl.start_chapter
        if start is not None and end is not None:
            max_chapter = _extend_max(max_chapter, start, end)
            bars.append(
                {
                    "id": f"storyline:{sl.id}",
                    "lane": "storyline",
                    "label": sl.name,
                    "start_chapter": int(start),
                    "end_chapter": int(end),
                    "status": sl.status,
                    "detail": sl.line_type,
                }
            )
        beats = sl.key_beats if isinstance(sl.key_beats, list) else []
        for i, beat in enumerate(beats):
            if not isinstance(beat, dict):
                continue
            cr = beat.get("chapter_range") or beat.get("chapter") or ""
            parsed = parse_chapter_range(str(cr)) if cr else None
            if not parsed:
                continue
            b_start, b_end = parsed
            max_chapter = _extend_max(max_chapter, b_start, b_end)
            bars.append(
                {
                    "id": f"storyline_beat:{sl.id}:{i}",
                    "lane": "storyline",
                    "label": f"{sl.name} · {beat.get('beat') or beat.get('milestone') or '节拍'}",
                    "start_chapter": b_start,
                    "end_chapter": b_end,
                    "status": "beat",
                    "detail": str(beat.get("milestone") or "")[:80] or None,
                }
            )

    # ── 势力活跃期 ──
    factions = (
        db.query(Faction)
        .filter(Faction.project_id == project_id)
        .order_by(Faction.sort_order)
        .all()
    )
    for fac in factions:
        extra = fac.extra if isinstance(fac.extra, dict) else {}
        period = extra.get("active_period") or extra.get("villain_timeline") or ""
        parsed = parse_chapter_range(str(period)) if period else None
        if not parsed:
            if period:
                bars.append(
                    {
                        "id": f"faction_point:{fac.id}",
                        "lane": "faction",
                        "label": fac.name,
                        "start_chapter": max_chapter,
                        "end_chapter": max_chapter,
                        "status": fac.alignment,
                        "detail": str(period)[:100],
                    }
                )
            continue
        f_start, f_end = parsed
        max_chapter = _extend_max(max_chapter, f_start, f_end)
        bars.append(
            {
                "id": f"faction:{fac.id}",
                "lane": "faction",
                "label": fac.name,
                "start_chapter": f_start,
                "end_chapter": f_end,
                "status": fac.alignment,
                "detail": str(period)[:80] or None,
            }
        )

    # ── 伏笔 ──
    foreshadows = db.query(Foreshadow).filter(Foreshadow.project_id == project_id).all()
    for fs in foreshadows:
        laid = fs.laid_chapter_number
        resolved = fs.resolved_chapter_number
        planned = fs.planned_resolve_chapter
        if laid is None:
            continue
        end = resolved or planned or laid
        max_chapter = _extend_max(max_chapter, laid, end)
        bars.append(
            {
                "id": f"foreshadow:{fs.id}",
                "lane": "foreshadow",
                "label": fs.title,
                "start_chapter": int(laid),
                "end_chapter": int(end),
                "status": fs.status,
                "detail": fs.foreshadow_type,
            }
        )

    # ── 读者承诺 ──
    promises = db.query(ReaderPromise).filter(ReaderPromise.project_id == project_id).all()
    for p in promises:
        src = p.source_chapter_number
        if src is None:
            continue
        window = p.expected_chapter_window
        end = int(src) + int(window) if window is not None else int(src)
        max_chapter = _extend_max(max_chapter, src, end)
        bars.append(
            {
                "id": f"promise:{p.id}",
                "lane": "promise",
                "label": (p.promise_text or "")[:40],
                "start_chapter": int(src),
                "end_chapter": end,
                "status": p.status,
                "detail": p.promise_type,
            }
        )

    # ── 主角境界里程碑（点状）──
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    power_systems = db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()
    protagonist_names = _collect_protagonist_anchor_names(characters)
    protagonist = next((c for c in characters if getattr(c, "role", None) == "protagonist"), None)
    built = build_protagonist_realm_timeline(
        plan_ctx,
        power_systems,
        protagonist_names=protagonist_names or None,
    )
    name_to_rank, _, _ = _build_realm_rank_map(power_systems)
    debrief_rows: list[Any] = []
    if protagonist and isinstance(getattr(protagonist, "extra", None), dict):
        raw_hist = protagonist.extra.get(DEBRIEF_REALM_MILESTONES_EXTRA_KEY)
        if isinstance(raw_hist, list):
            debrief_rows = [x for x in raw_hist if isinstance(x, dict)]
    merged = merge_outline_and_debrief_realm_milestones(
        built["milestones"],
        debrief_rows,
        name_to_rank,
    )
    for m in merged:
        ch_num = _safe_int(m.get("chapter_number"), 0)
        if ch_num < 1:
            continue
        max_chapter = _extend_max(max_chapter, ch_num)
        bars.append(
            {
                "id": f"realm:{ch_num}:{m.get('realm_name', '')}",
                "lane": "realm",
                "label": str(m.get("realm_name") or "境界"),
                "start_chapter": ch_num,
                "end_chapter": ch_num,
                "status": m.get("source"),
                "detail": (m.get("character_change") or m.get("chapter_title") or "")[:80],
            }
        )

    lanes = [
        {"id": "volume", "label": "卷 / 阶段", "description": "卷跨度与 phase"},
        {"id": "chapter", "label": "章节正文", "description": "已创建章节的写作状态"},
        {"id": "storyline", "label": "故事线", "description": "主线/支线起止与 key_beats"},
        {"id": "faction", "label": "势力", "description": "extra.active_period 解析"},
        {"id": "foreshadow", "label": "伏笔", "description": "埋下→计划/实际回收"},
        {"id": "promise", "label": "读者承诺", "description": "源章→兑现窗口"},
        {"id": "realm", "label": "境界里程碑", "description": "大纲人物变化 + 复盘快照"},
    ]

    return {
        "max_chapter": max(1, max_chapter),
        "chapter_plan_count": len(plan_nodes),
        "written_chapter_count": len(chapters),
        "lanes": lanes,
        "bars": bars,
    }
