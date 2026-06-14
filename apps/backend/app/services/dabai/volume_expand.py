"""dabai 实验书架 — 按卷懒展开章纲（bootstrap 之后的写作期入口）。

bootstrap（dabai/pipeline.py）只展开第 1 卷章纲，卷 2+ 仅有 DabaiVolume 卷骨架。
本模块从 dabai_* 表重建 pipeline ctx，复用 dabai.steps.aiter_chapter_batches
逐批生成目标卷章纲并落库（持久化优先：每批立即 commit，中断不丢已生成部分）。

重做语义（同番茄线约定）：
  - 未满卷：增量补全（从已有章数+1 起批，prev_tail / realm_floor 从末章接续）；
  - 满卷：需 force=True 删旧重做，否则抛 VolumeAlreadyFull。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Awaitable, Callable

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject, DabaiVolume
from app.services.dabai.lab_narrative_state import (
    build_bridge_block,
    build_narrative_state_block,
    build_semantic_outline_block,
)
from app.services.dabai_persist import make_chapter_outline_row

logger = logging.getLogger("dabai.volume_expand")

CallFn = Callable[[str, str, str, dict | None], Awaitable[Any]]


class VolumeAlreadyFull(RuntimeError):
    """目标卷章纲已满且未指定 force，拒绝重复展开。"""


def merge_beat_rows(existing: list, new: list) -> list:
    """按 chapter_number 合并节拍行（增量展开时保留前窗口）。"""
    by_num: dict[int, dict] = {}
    for r in existing + new:
        if isinstance(r, dict):
            by_num[int(r.get("chapter_number") or 0)] = r
    return [by_num[k] for k in sorted(by_num) if k > 0]


def build_expand_ctx(p: DabaiProject) -> dict:
    """从 dabai_* 表重建章纲 prompt 所需 ctx（与 bootstrap 期 ctx 键对齐）。

    规划层产物（反派阶梯/谜题排程/书名）从 project.extra 回读，
    使卷 2+ 章纲与 bootstrap 期拿到同一份富上下文（ctx_rich 注入块）。
    """
    extra = p.extra or {}
    return {
        "logline": p.logline,
        "benchmark": p.benchmark or {},
        "positioning": p.positioning or {},
        "golden_finger": p.golden_finger or {},
        "power_ladder": p.power_ladder or {},
        "antagonist_ladder": extra.get("antagonist_ladder") or [],
        "mystery_schedule": extra.get("mystery_schedule") or {},
        "title_blurb": extra.get("title_blurb") or {},
        # 规划快照（bootstrap storylines 步一次产出，不随写作期变化）。
        # 用于 chapter_design_context 的 relations_block（开局关系张力）与
        # assets_block（剧情资产台账，含★本卷必须兑现登场★标记）。
        # 存量书（建于此修复之前）extra 无此键，降级为空 dict → 两块静默为空。
        "story_assets": extra.get("story_assets") or {},
        "factions": [{"name": f.name, "stance": f.stance, "role": f.role,
                      "power_tier": f.power_tier, "note": f.note,
                      "locations": f.locations or []} for f in p.factions],
        "characters": [{"name": c.name, "role": c.role, "tier": c.tier,
                        "start_realm": c.start_realm, "persona": c.persona,
                        "function": c.function, **(c.extra or {})} for c in p.characters],
        "storylines": [{"name": s.name, "type": s.type, "summary": s.summary,
                        "nodes": s.nodes or [],
                        "bound_characters": s.bound_characters or []}
                       for s in p.storylines],
        "volumes": [_volume_dict(v) for v in p.volumes],
    }


def _volume_dict(v: DabaiVolume) -> dict:
    return {
        "volume_number": v.volume_number, "title": v.title, "phase": v.phase,
        "planned_chapters": int(v.planned_chapters or 0),
        "big_beats": v.big_beats or [], "volume_climax": v.volume_climax,
        "end_hook": v.end_hook,
        "realm_start_rank": v.realm_start_rank, "realm_end_rank": v.realm_end_rank,
        "extra": v.extra or {},
    }


def _chapter_tail(ch: DabaiChapterOutline | None) -> str:
    if ch is None:
        return ""
    return (ch.end_hook or ch.shuang_payoff or "").strip()


async def _enrich_expand_ctx(
    db: Session,
    p: DabaiProject,
    volume: DabaiVolume,
    ctx: dict,
    window: dict,
) -> None:
    """注入 Layer 2 情节状态 + 硬承接 + 质检回灌（卷展开专用）。"""
    offset = window["chapter_offset"]
    start = window["start_chapter"]
    before = offset + start
    gbs = before
    gbe = offset + window["planned"]

    vols = sorted(p.volumes, key=lambda v: v.volume_number)
    prev_vol = next(
        (v for v in vols if v.volume_number == volume.volume_number - 1), None,
    )

    from app.services.dabai.lab_qc_feedback import (
        build_chapter_range_qc_block,
        build_project_qc_issue_block,
    )

    extra: list[str] = []
    qc_book = build_project_qc_issue_block(db, p.id)
    if qc_book:
        extra.append(qc_book)
        ctx["qc_feedback"] = qc_book
    qc_range = build_chapter_range_qc_block(
        db, p.id, chapter_from=gbs, chapter_to=gbe,
    )
    if qc_range:
        extra.append(qc_range)

    semantic = await build_semantic_outline_block(db, p, before_chapter=before)
    if semantic:
        extra.append(semantic)

    narrative = build_narrative_state_block(
        db, p, before_chapter=before, prev_volume=prev_vol, extra_blocks=extra,
    )
    if narrative:
        ctx["narrative_state"] = narrative
        ctx["story_so_far"] = narrative

    ctx["bridge_block"] = build_bridge_block(
        db, p,
        before_chapter=before,
        prev_tail_fallback=window.get("prev_tail") or "",
    )
    ctx.setdefault("generated_chapter_outlines", [])


def resolve_expand_window(
    db: Session, p: DabaiProject, volume: DabaiVolume, *, force: bool = False,
) -> dict:
    """解析目标卷的展开窗口与承接种子。

    全局章号区间 = (offset, offset+planned]，offset 为之前各卷 planned_chapters 之和
    （与前端 groupByVolume 的切片口径一致）。

    Returns:
        dict: chapter_offset / planned / start_chapter（卷内 1-based）/
              prev_tail / realm_floor / existing_ids（force 时待删行 id）。

    Raises:
        VolumeAlreadyFull: 卷已满且 force=False。
    """
    vols = sorted(p.volumes, key=lambda v: v.volume_number)
    offset = sum(int(v.planned_chapters or 0) for v in vols
                 if v.volume_number < volume.volume_number)
    planned = int(volume.planned_chapters or 0)
    existing = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == p.id,
            DabaiChapterOutline.chapter_number > offset,
            DabaiChapterOutline.chapter_number <= offset + planned,
        )
        .order_by(DabaiChapterOutline.chapter_number)
        .all()
    )
    if existing and len(existing) >= planned and not force:
        raise VolumeAlreadyFull(
            f"第 {volume.volume_number} 卷章纲已满（{len(existing)}/{planned}），"
            "重做请传 force=true"
        )

    if force or not existing:
        # 全量展开：承接上一卷末章钩子（无上卷或上卷未展开则用卷骨架 end_hook 兜底）
        prev_ch = (
            db.query(DabaiChapterOutline)
            .filter(DabaiChapterOutline.project_id == p.id,
                    DabaiChapterOutline.chapter_number <= offset)
            .order_by(DabaiChapterOutline.chapter_number.desc())
            .first()
        )
        prev_vol = next(
            (v for v in vols if v.volume_number == volume.volume_number - 1), None)
        prev_tail = _chapter_tail(prev_ch) or ((prev_vol.end_hook or "").strip()
                                               if prev_vol else "")
        return {
            "chapter_offset": offset, "planned": planned, "start_chapter": 1,
            "prev_tail": prev_tail, "realm_floor": None,
            "existing_ids": [c.id for c in existing] if force else [],
        }

    # 未满卷增量补全：从已有末章接续
    last = existing[-1]
    return {
        "chapter_offset": offset, "planned": planned,
        "start_chapter": len(existing) + 1,
        "prev_tail": _chapter_tail(last),
        "realm_floor": last.realm_rank,
        "existing_ids": [],
    }


async def aiter_volume_expand(
    db: Session, p: DabaiProject, volume: DabaiVolume, cfg: Any, call: CallFn,
    *, force: bool = False,
) -> AsyncIterator[dict]:
    """逐批展开目标卷章纲并落库，yield SSE 友好事件 dict。

    事件：expand_start → chapter_batch×N → done；异常由调用方（路由层）兜底。
    每批生成后立即 commit（持久化优先，中断不丢已生成批次）。
    """
    from dabai.steps import aiter_chapter_batches

    window = resolve_expand_window(db, p, volume, force=force)
    if window["existing_ids"]:
        (db.query(DabaiChapterOutline)
         .filter(DabaiChapterOutline.id.in_(window["existing_ids"]))
         .delete(synchronize_session=False))
        db.commit()
        logger.info("dabai 卷展开 force 删旧 project=%s vol=%d 删 %d 章",
                    p.id, volume.volume_number, len(window["existing_ids"]))

    offset, planned = window["chapter_offset"], window["planned"]
    yield {
        "event": "expand_start", "volume_number": volume.volume_number,
        "chapter_from": offset + window["start_chapter"],
        "chapter_to": offset + planned, "mode": "force" if force else
        ("incremental" if window["start_chapter"] > 1 else "full"),
    }

    ctx = build_expand_ctx(p)
    await _enrich_expand_ctx(db, p, volume, ctx, window)
    created = 0
    async for batch, gbs, gbe in aiter_chapter_batches(
        ctx, call, cfg, _volume_dict(volume),
        start_chapter=window["start_chapter"], chapter_offset=offset,
        prev_tail=window["prev_tail"], realm_floor=window["realm_floor"],
    ):
        for ch in batch:
            db.add(make_chapter_outline_row(p.id, volume.id, ch))
        db.commit()
        created += len(batch)
        yield {"event": "chapter_batch", "batch_start": gbs, "batch_end": gbe,
               "total": created}

    # 节拍序列快照落库（持久化优先；增量展开时与已有窗口合并）
    beats = ctx.get("beat_sequence") or []
    if beats:
        key = f"beat_sequence_vol{volume.volume_number}"
        prior = (p.extra or {}).get(key) or []
        merged = merge_beat_rows(
            prior if isinstance(prior, list) else [], beats,
        )
        p.extra = {**(p.extra or {}), key: merged}
        db.commit()

    from app.services.dabai.lab_outline_lint import run_dabai_project_linter

    db.refresh(p)
    linter_report = run_dabai_project_linter(db, p, cfg)
    yield {
        "event": "linter_done",
        "status": linter_report.get("status"),
        "score": linter_report.get("score"),
        "issue_count": linter_report.get("issue_count"),
        "critical_count": linter_report.get("critical_count"),
    }
    yield {"event": "done", "volume_number": volume.volume_number,
           "created": created}
