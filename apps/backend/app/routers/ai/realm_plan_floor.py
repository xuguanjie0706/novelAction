"""
realm_plan_floor.py — 章级「计划境界 floor」确定性对齐

设计动机（境界记录滞后根因修复）：
  原系统 current_realm 只由复盘 AI 事后从正文反推，存在两个滞后：
  ① 复盘 AI 抽不到/抽错境界 → 记录不更新；
  ② 质检发生在复盘提交之前 → 本章合理突破必先被旧记录误判一次。

  本模块用「章纲 power_milestone（实力里程碑）」作为**确定性**来源，
  把主角境界推进到本章计划值（只升不降的 floor）：
  - persist_planned_realm_floor：复盘提交时落库（方向2，权威推进，不再单纯依赖 LLM）。
  - project_planned_realm_floor：质检构造 character_states 时**只读**投影（方向3，止血，不写库）。

设计约束：
- 只推进 role==protagonist 的角色；只在计划 rank 高于当前 rank 时推进（floor，绝不降级）。
- power_milestone 须含进阶语义动词才视为主角突破，避免把「反派境界」误算到主角头上。
- 复用 realm_tracker.apply_realm_progression_side_effects（arc_stages / 里程碑记忆一致）。
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.models import Character, PowerSystem
from app.routers.ai.realm_tracker import apply_realm_progression_side_effects
from app.routers.outline.helpers.realm_whitelist import build_realm_rank_map
from app.utils.chapter_numbering import display_chapter_number

logger = logging.getLogger(__name__)


def _build_name_to_rank(db: Any, project_id: Any) -> dict[str, int]:
    systems = db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()
    name_to_rank, _, _ = build_realm_rank_map(systems)
    return name_to_rank or {}


def _planned_realm_from_chapter(
    db: Any, project: Any, chapter: Any, name_to_rank: dict[str, int]
) -> tuple[str | None, int | None]:
    """本章主角「计划境界」(label, rank)。

    方向1：统一走章级境界轴（卷起止插值 + 里程碑锚点），覆盖无显式里程碑的章节；
    无境界体系 / 无章纲锚点时返回 (None, None)。
    """
    from app.services.ai.realm_axis import expected_realm_for_chapter

    return expected_realm_for_chapter(db, project, chapter, name_to_rank)


def _protagonists(db: Any, project_id: Any) -> list[Character]:
    return (
        db.query(Character)
        .filter(Character.project_id == project_id, Character.role == "protagonist")
        .all()
    )


def project_planned_realm_floor(db: Any, project: Any, chapter: Any) -> dict[str, dict[str, Any]]:
    """只读：返回 {protagonist_name: {"realm": label, "rank": rank}}，仅当计划 rank 高于当前。

    供质检 character_states 构造时投影，使质检基准为「本章计划境界」而非滞后记录。不写库。
    """
    name_to_rank = _build_name_to_rank(db, project.id)
    label, rank = _planned_realm_from_chapter(db, project, chapter, name_to_rank)
    if not label or rank is None:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for c in _protagonists(db, project.id):
        cur_rank = c.realm_rank if isinstance(c.realm_rank, int) else -1
        if rank > cur_rank:
            out[c.name] = {"realm": label, "rank": rank}
    return out


def persist_planned_realm_floor(db: Any, project: Any, chapter: Any) -> dict | None:
    """落库：把主角境界确定性推进到本章计划 floor（只升不降）。

    复盘提交后调用，作为 LLM 抽取的兜底。返回 None 表示无推进。
    """
    name_to_rank = _build_name_to_rank(db, project.id)
    label, rank = _planned_realm_from_chapter(db, project, chapter, name_to_rank)
    if not label or rank is None:
        return None

    chapter_number = display_chapter_number(getattr(chapter, "title", "") or "", getattr(chapter, "sort_order", 0) or 0)
    advanced: list[str] = []
    new_chunks = []
    for c in _protagonists(db, project.id):
        cur_rank = c.realm_rank if isinstance(c.realm_rank, int) else 0
        if rank <= cur_rank:
            continue
        before_realm = c.current_realm
        before_rank = c.realm_rank
        # 追加 plan_auto 来源里程碑（与 debrief_realm_milestones 同结构，去重同章同名）
        extra = dict(c.extra) if isinstance(c.extra, dict) else {}
        hist = [h for h in (extra.get("debrief_realm_milestones") or []) if isinstance(h, dict)]
        if not any(
            h.get("chapter_number") == chapter_number and h.get("realm_name") == label
            for h in hist
        ):
            hist.append({
                "chapter_number": chapter_number,
                "chapter_id": str(chapter.id),
                "realm_name": label,
                "realm_rank": rank,
                "source": "plan_auto",
            })
            extra["debrief_realm_milestones"] = hist
            c.extra = extra
        mc = apply_realm_progression_side_effects(
            c,
            realm_label=label,
            rank_snap=rank,
            chapter_number=chapter_number,
            chapter_id=str(chapter.id),
            chapter_title=getattr(chapter, "title", "") or "",
            before_realm=before_realm,
            before_rank=before_rank,
            project_id=str(project.id),
            chapter_uuid=chapter.id if isinstance(chapter.id, UUID) else UUID(str(chapter.id)),
            name_to_rank=name_to_rank,
        )
        if mc is not None:
            db.add(mc)
            new_chunks.append(mc)
        advanced.append(f"{c.name}:{before_realm or '?'}→{label}")

    if not advanced:
        return None
    db.commit()
    logger.info("realm_plan_floor 推进 project=%s chapter=%s %s", project.id, chapter.id, advanced)
    return {"advanced": advanced, "memory_chunks": new_chunks}
