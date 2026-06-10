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
from app.models.dabai_lab import DabaiAsset, DabaiClue, DabaiMemory, DabaiRelation
from app.services.dabai_persist import make_chapter_outline_row

logger = logging.getLogger("dabai.volume_expand")

CallFn = Callable[[str, str, str, dict | None], Awaitable[Any]]


class VolumeAlreadyFull(RuntimeError):
    """目标卷章纲已满且未指定 force，拒绝重复展开。"""


def build_expand_ctx(p: DabaiProject) -> dict:
    """从 dabai_* 表重建章纲 prompt 所需 ctx（与 bootstrap 期 ctx 键对齐）。"""
    return {
        "logline": p.logline,
        "benchmark": p.benchmark or {},
        "positioning": p.positioning or {},
        "golden_finger": p.golden_finger or {},
        "power_ladder": p.power_ladder or {},
        "factions": [{"name": f.name, "stance": f.stance, "role": f.role,
                      "power_tier": f.power_tier, "note": f.note} for f in p.factions],
        "characters": [{"name": c.name, "role": c.role, "tier": c.tier,
                        "start_realm": c.start_realm, "persona": c.persona,
                        "function": c.function, **(c.extra or {})} for c in p.characters],
        "storylines": [{"name": s.name, "type": s.type, "summary": s.summary}
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
    }


def _chapter_tail(ch: DabaiChapterOutline | None) -> str:
    if ch is None:
        return ""
    return (ch.end_hook or ch.shuang_payoff or "").strip()


def build_story_so_far(
    db: Session, p: DabaiProject, volume: DabaiVolume, chapter_offset: int,
) -> str:
    """组装「前情与既定事实」注入块（防凭空生成的核心）。

    四个来源，任一为空则该段省略；全空返回空串（新书第1卷展开时自然为空）：
      ① 上文章纲轨迹：offset 前最后 5 章（标题/爽点/钩子/境界档）+ 上一卷收束；
      ② 复盘记忆（dabai_memories）：已写正文经复盘提取的事实，重要度优先 Top-8；
      ③ 未回收线索（dabai_clues open）：埋设越早越优先，要求本卷择机回收；
      ④ 台账：主角 active 资产 + 人物关系最新态度（与 lab_ledger 同口径的紧凑版）。
    """
    parts: list[str] = []

    prev_chs = (
        db.query(DabaiChapterOutline)
        .filter(DabaiChapterOutline.project_id == p.id,
                DabaiChapterOutline.chapter_number <= chapter_offset)
        .order_by(DabaiChapterOutline.chapter_number.desc())
        .limit(5).all()
    )
    if prev_chs:
        lines = [
            f"  第{c.chapter_number}章《{(c.title or '').strip()}》："
            f"{(c.shuang_payoff or c.yinbao or '')[:40]}"
            + (f"；末钩：{(c.end_hook or '')[:40]}" if c.end_hook else "")
            + (f"；境界档{c.realm_rank}" if c.realm_rank else "")
            for c in reversed(prev_chs)
        ]
        parts.append("① 上文章纲轨迹（最近5章，新卷开篇必须顺着这条线走）：\n"
                     + "\n".join(lines))
        prev_vol = next((v for v in sorted(p.volumes, key=lambda x: x.volume_number)
                         if v.volume_number == volume.volume_number - 1), None)
        if prev_vol and (prev_vol.volume_climax or prev_vol.end_hook):
            parts.append(f"  上一卷收束：高潮「{(prev_vol.volume_climax or '')[:60]}」"
                         f"／卷末钩子「{(prev_vol.end_hook or '')[:60]}」")

    mems = (
        db.query(DabaiMemory)
        .filter(DabaiMemory.project_id == p.id)
        .order_by(DabaiMemory.importance.desc(), DabaiMemory.chapter_number.desc())
        .limit(8).all()
    )
    if mems:
        parts.append("② 已写正文既定事实（复盘记忆，不可矛盾、不可重置）：\n"
                     + "\n".join(f"  - [第{m.chapter_number}章]{m.content[:60]}"
                                 for m in mems))

    clues = (
        db.query(DabaiClue)
        .filter(DabaiClue.project_id == p.id, DabaiClue.status == "open")
        .order_by(DabaiClue.chapter_planted)
        .limit(8).all()
    )
    if clues:
        parts.append("③ 未回收线索（埋设越早越优先，本卷至少择机回收 1-2 条，"
                     "在对应章 yinbao/end_hook 里兑现）：\n"
                     + "\n".join(f"  - [第{c.chapter_planted}章埋]{c.title}"
                                 f"：{(c.description or '')[:40]}" for c in clues))

    protag = next((c.name for c in p.characters if (c.role or "").startswith("主角")),
                  p.characters[0].name if p.characters else "")
    assets = (
        db.query(DabaiAsset)
        .filter(DabaiAsset.project_id == p.id, DabaiAsset.status == "active")
        .order_by(DabaiAsset.kind, DabaiAsset.acquired_chapter)
        .limit(12).all()
    )
    rels = (
        db.query(DabaiRelation)
        .filter(DabaiRelation.project_id == p.id, DabaiRelation.from_name == protag)
        .limit(10).all()
    ) if protag else []
    ledger_lines = []
    if assets:
        ledger_lines.append("  资产（禁用台账外能力；已消耗/遗失不得再用）："
                            + "、".join(a.name for a in assets))
    if rels:
        ledger_lines.append("  关系（最新态度，变化须有剧情交代）："
                            + "；".join(f"{r.to_name}={r.attitude or '中立'}" for r in rels))
    if ledger_lines:
        parts.append("④ 主角台账：\n" + "\n".join(ledger_lines))

    return "\n".join(parts)


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
    # 前情回灌：上文章纲轨迹/复盘记忆/未回收线索/台账 → prompt「既定事实」块
    story = build_story_so_far(db, p, volume, offset)
    if story:
        ctx["story_so_far"] = story
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

    yield {"event": "done", "volume_number": volume.volume_number,
           "created": created}
