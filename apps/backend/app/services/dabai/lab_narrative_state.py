"""实验书架「情节状态」块 — 章纲与成文共用的 Layer 2 上下文。

聚合章纲计划、正文实际、复盘记忆、线索/台账变更，供：
  - 卷展开 / bootstrap 分批章纲 prompt（``build_narrative_state_block``）；
  - 写章 prompt（``build_chapter_timeline_block`` + ``build_world_snapshot_block``）；
  - 批间承接（``build_bridge_block`` / ``format_bridge_from_outline``）。

设计动机：不计 token 时，后面章纲须读「已发生世界」而非仅 120 字钩子；
与 ``lab_chapter_archive`` 同源数据，但按 prompt 可读性渲染为文本块。
"""
from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject, DabaiVolume
from app.models.dabai_lab import DabaiAsset, DabaiClue, DabaiMemory, DabaiRelation

_MEM_LABELS = {
    "summary": "摘要", "fact": "事实", "event": "事件",
    "state": "状态", "relation": "关系",
}


def _tail(text: str, n: int) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    return t[-n:] if len(t) > n else t


def _one_line_plan(ch: DabaiChapterOutline) -> str:
    parts = [
        f"场景:{(ch.location or '')[:24]}",
        f"爽点:{(ch.shuang_type or '')[:12]}",
    ]
    spine = "→".join(
        p for p in (
            (ch.yaqu_setup or "")[:28],
            (ch.emotion_turn or "")[:20],
            (ch.yinbao or "")[:28],
            (ch.shuang_payoff or "")[:28],
        ) if p
    )
    if spine:
        parts.append(spine)
    if ch.end_hook:
        parts.append(f"钩:{ch.end_hook[:36]}")
    if ch.realm_rank:
        parts.append(f"境档{ch.realm_rank}")
    return "；".join(parts)


def _asset_change_label(a: DabaiAsset, chapter: int) -> str | None:
    if a.acquired_chapter == chapter:
        return "获得"
    if a.status_chapter == chapter and a.status in ("consumed", "lost"):
        return "消耗" if a.status == "consumed" else "失去"
    return None


def build_chapter_timeline_block(
    db: Session,
    project: DabaiProject,
    *,
    before_chapter: int,
) -> str:
    """全书第 1～before_chapter-1 章情节时间轴（计划 vs 实际，不截断章数）。"""
    if before_chapter <= 1:
        return ""

    chapters = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project.id,
            DabaiChapterOutline.chapter_number < before_chapter,
        )
        .order_by(DabaiChapterOutline.chapter_number)
        .all()
    )
    if not chapters:
        return ""

    mems_by_ch: dict[int, list[DabaiMemory]] = defaultdict(list)
    for m in db.query(DabaiMemory).filter(DabaiMemory.project_id == project.id).all():
        mems_by_ch[int(m.chapter_number or 0)].append(m)

    assets = db.query(DabaiAsset).filter(DabaiAsset.project_id == project.id).all()
    rel_by_ch: dict[int, list[str]] = defaultdict(list)
    for r in db.query(DabaiRelation).filter(DabaiRelation.project_id == project.id).all():
        for h in (r.history or []):
            if not isinstance(h, dict) or h.get("chapter") is None:
                continue
            ch_num = int(h["chapter"])
            if ch_num >= before_chapter:
                continue
            rel_by_ch[ch_num].append(
                f"{r.from_name}→{r.to_name}={h.get('attitude', '')}"
                + (f"({h.get('reason', '')[:20]})" if h.get("reason") else "")
            )

    lines: list[str] = []
    for ch in chapters:
        num = int(ch.chapter_number or 0)
        written = bool((ch.content or "").strip())
        mems = mems_by_ch.get(num, [])
        summary = next((m.content for m in mems if m.mem_type == "summary"), "")
        core = [m.content[:80] for m in mems if m.mem_type != "summary"][:4]

        status = "已写+复盘" if (written and mems) else ("已写" if written else "仅章纲")
        line = f"  第{num}章《{(ch.title or '')[:16]}》[{status}]"
        line += f"\n    计划：{_one_line_plan(ch)}"

        if summary:
            line += f"\n    实际摘要：{summary[:200]}"
        elif written:
            line += f"\n    正文收束：…{_tail(ch.content or '', 220)}"
        for ev in core:
            line += f"\n    · {ev}"

        asset_bits = [
            f"{a.name}({lbl})"
            for a in assets
            if (lbl := _asset_change_label(a, num))
        ]
        if asset_bits:
            line += f"\n    资产：{'、'.join(asset_bits[:6])}"
        if rel_by_ch.get(num):
            line += f"\n    关系：{'；'.join(rel_by_ch[num][:4])}"

        lines.append(line)

    return (
        "【全书情节时间轴（第1章至第"
        f"{before_chapter - 1}章；已写事实不可推翻，仅章纲条目为计划未发生）】\n"
        + "\n".join(lines)
    )


def build_world_snapshot_block(
    db: Session,
    project: DabaiProject,
    *,
    before_chapter: int,
) -> str:
    """当前世界快照：open 线索、主角台账、已失效资产。"""
    if before_chapter <= 1:
        return ""

    parts: list[str] = []
    protag = next(
        (c.name for c in project.characters if (c.role or "").startswith("主角")),
        project.characters[0].name if project.characters else "",
    )

    clues = (
        db.query(DabaiClue)
        .filter(
            DabaiClue.project_id == project.id,
            DabaiClue.status == "open",
            DabaiClue.chapter_planted < before_chapter,
        )
        .order_by(DabaiClue.chapter_planted)
        .all()
    )
    if clues:
        parts.append(
            "▸未回收线索（埋设越早越优先，本卷须择机回收）：\n"
            + "\n".join(
                f"  - [第{c.chapter_planted}章埋]《{c.title}》：{(c.description or '')[:60]}"
                for c in clues
            )
        )

    active = (
        db.query(DabaiAsset)
        .filter(
            DabaiAsset.project_id == project.id,
            DabaiAsset.status == "active",
        )
        .order_by(DabaiAsset.kind, DabaiAsset.acquired_chapter)
        .all()
    )
    dead = (
        db.query(DabaiAsset)
        .filter(
            DabaiAsset.project_id == project.id,
            DabaiAsset.status.in_(("consumed", "lost")),
        )
        .all()
    )
    ledger: list[str] = []
    if active:
        ledger.append(
            "  可用资产："
            + "、".join(
                f"{a.name}({a.kind},第{a.acquired_chapter or '?'}章得)"
                for a in active[:20]
            )
        )
    if dead:
        ledger.append(
            "  已消耗/遗失（禁止再用）："
            + "、".join(f"{a.name}" for a in dead[:15])
        )
    if protag:
        rels = (
            db.query(DabaiRelation)
            .filter(
                DabaiRelation.project_id == project.id,
                DabaiRelation.from_name == protag,
            )
            .all()
        )
        if rels:
            ledger.append(
                "  关系最新态度："
                + "；".join(f"{r.to_name}={r.attitude or '中立'}" for r in rels[:12])
            )
    if ledger:
        parts.append("▸主角台账与世界状态：\n" + "\n".join(ledger))

    last_written = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project.id,
            DabaiChapterOutline.chapter_number < before_chapter,
            DabaiChapterOutline.content.isnot(None),
        )
        .order_by(DabaiChapterOutline.chapter_number.desc())
        .first()
    )
    if last_written and last_written.realm_rank:
        parts.append(
            f"▸末章已知主角境界档：第{last_written.realm_rank}档"
            f"（第{last_written.chapter_number}章末）"
        )

    if not parts:
        return ""
    return "【当前世界快照（章纲/正文均须与此一致）】\n" + "\n\n".join(parts)


def build_bridge_block(
    db: Session,
    project: DabaiProject,
    *,
    before_chapter: int,
    prev_tail_fallback: str = "",
) -> str:
    """硬承接包：优先上章正文末段，其次完整五拍章纲，最后钩子兜底。"""
    if before_chapter <= 1:
        return ""

    prev = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project.id,
            DabaiChapterOutline.chapter_number == before_chapter - 1,
        )
        .first()
    )
    if not prev:
        tail = (prev_tail_fallback or "").strip()
        if not tail:
            return ""
        return (
            f"\n【硬承接（第{before_chapter}章开篇）】上一卷/上文末钩：「{tail[:200]}」。"
            f"第{before_chapter}章必须紧接此钩子起笔，禁止另起炉灶。\n"
        )

    content = (prev.content or "").strip()
    if content:
        hook = (prev.end_hook or "").strip()
        parts = [
            f"\n【硬承接（第{before_chapter}章开篇须紧接上一瞬间）】",
            f"上一章（第{prev.chapter_number}章）正文末段（已发生，不可推翻）：",
            _tail(content, 1200),
        ]
        if hook:
            parts.append(f"章纲计划末钩（以正文实际收束为准）：{hook[:120]}")
        parts.append(
            f"★第{before_chapter}章第一个画面必须正面回应上述结尾，"
            "禁止时间回溯、禁止无视末钩。\n"
        )
        return "\n".join(parts)

    return format_bridge_from_outline(prev, before_chapter, prev_tail_fallback)


def format_bridge_from_outline(
    prev: DabaiChapterOutline | dict,
    next_chapter: int,
    prev_tail_fallback: str = "",
) -> str:
    """从章纲 dict/ORM 行格式化承接块（bootstrap 批间无 DB 时用）。"""
    if isinstance(prev, dict):
        num = int(prev.get("chapter_number") or 0)
        title = str(prev.get("title") or "")
        fields = [
            ("憋屈", prev.get("yaqu_setup")),
            ("转折", prev.get("emotion_turn")),
            ("引爆", prev.get("yinbao")),
            ("爽点", prev.get("shuang_payoff")),
            ("钩子", prev.get("end_hook")),
        ]
    else:
        num = int(prev.chapter_number or 0)
        title = prev.title or ""
        fields = [
            ("憋屈", prev.yaqu_setup),
            ("转折", prev.emotion_turn),
            ("引爆", prev.yinbao),
            ("爽点", prev.shuang_payoff),
            ("钩子", prev.end_hook),
        ]

    hook = str(fields[-1][1] or prev_tail_fallback or "").strip()
    beat_lines = [f"  {label}：{str(val)[:120]}" for label, val in fields if val]
    if not beat_lines and hook:
        return _carry_block_legacy(hook, next_chapter)

    body = "\n".join(beat_lines) if beat_lines else f"  末钩：{hook[:120]}"
    return (
        f"\n【硬承接（第{next_chapter}章须顺接上章章纲）】"
        f"第{num}章《{title[:16]}》五拍收束：\n{body}\n"
        f"★第{next_chapter}章开篇必须紧接上述钩子/爽点收束，禁止另起炉灶。\n"
    )


def _carry_block_legacy(prev_tail: str, gbs: int) -> str:
    prev_tail = (prev_tail or "").strip()
    if not prev_tail:
        return ""
    return (
        f"\n【上文结尾（硬性承接）】前一章末钩/爽点：「{prev_tail[:200]}」。"
        f"第{gbs}章必须顺着它起。\n"
    )


def format_generated_outlines_block(outlines: list[dict]) -> str:
    """本 run 已生成章纲全文（bootstrap/卷展开批间回灌）。"""
    if not outlines:
        return ""
    lines: list[str] = []
    for ch in outlines:
        num = int(ch.get("chapter_number") or 0)
        title = str(ch.get("title") or "")
        block = [
            f"  第{num}章《{title[:16]}》",
            f"    场景:{ch.get('location', '')} 爽点:{ch.get('shuang_type', '')} "
            f"境档:{ch.get('realm_rank', '?')}",
            f"    憋屈:{str(ch.get('yaqu_setup', ''))[:80]}",
            f"    转折:{str(ch.get('emotion_turn', ''))[:60]}",
            f"    引爆:{str(ch.get('yinbao', ''))[:80]}",
            f"    爽点:{str(ch.get('shuang_payoff', ''))[:80]}",
            f"    钩子:{str(ch.get('end_hook', ''))[:80]}",
            f"    见证:{('、'.join(ch.get('witnesses') or [])[:60])}",
        ]
        lines.append("\n".join(block))
    return (
        "【本卷已生成章纲（本批须与之衔接；shuang_type/location/境界须单调延续）】\n"
        + "\n\n".join(lines)
    )


def build_narrative_state_block(
    db: Session,
    project: DabaiProject,
    *,
    before_chapter: int,
    prev_volume: DabaiVolume | None = None,
    extra_blocks: list[str] | None = None,
) -> str:
    """章纲 prompt 用 Layer 2：时间轴 + 世界快照 + 可选附加块（语义/QC）。"""
    parts: list[str] = []

    timeline = build_chapter_timeline_block(db, project, before_chapter=before_chapter)
    if timeline:
        parts.append(timeline)

    snapshot = build_world_snapshot_block(db, project, before_chapter=before_chapter)
    if snapshot:
        parts.append(snapshot)

    if prev_volume and (prev_volume.volume_climax or prev_volume.end_hook):
        parts.append(
            "▸上一卷收束："
            f"高潮「{(prev_volume.volume_climax or '')[:80]}」"
            f"／卷末钩「{(prev_volume.end_hook or '')[:80]}」"
        )

    for block in extra_blocks or []:
        if block and block.strip():
            parts.append(block.strip())

    return "\n\n".join(parts)


async def build_semantic_outline_block(
    db: Session,
    project: DabaiProject,
    *,
    before_chapter: int,
) -> str:
    """章纲展开：按「即将写的下一章」语义召回既往事实（pgvector）。"""
    from app.services.dabai.lab_embedding import semantic_search_dabai

    last = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project.id,
            DabaiChapterOutline.chapter_number < before_chapter,
        )
        .order_by(DabaiChapterOutline.chapter_number.desc())
        .first()
    )
    query_parts = [project.logline or "", project.title or ""]
    if last:
        query_parts.extend([
            str(last.title or ""),
            str(last.shuang_type or ""),
            str(last.yinbao or ""),
            "、".join(list(last.involved_characters or [])[:6]),
        ])
    query = " ".join(p for p in query_parts if p.strip())[:1000]
    if not query:
        return ""

    hits = await semantic_search_dabai(
        db, project.id, query, top_k=10, max_chapter=before_chapter,
    )
    if not hits:
        return ""
    hits.sort(key=lambda m: m.chapter_number or 0)
    lines = [
        f"  - 第{m.chapter_number}章[{_MEM_LABELS.get(m.mem_type, m.mem_type)}] {m.content}"
        for m in hits
    ]
    return (
        "▸语义相关既往事实（旧角色/恩怨/承诺；禁止矛盾）：\n" + "\n".join(lines)
    )


def build_story_so_far(
    db: Session, p: DabaiProject, volume: DabaiVolume, chapter_offset: int,
    *, start_chapter: int = 1,
) -> str:
    """兼容旧入口：委托 ``build_narrative_state_block``（修正增量补全 before 章号）。"""
    before = chapter_offset + max(1, start_chapter)
    prev_vol = next(
        (v for v in sorted(p.volumes, key=lambda x: x.volume_number)
         if v.volume_number == volume.volume_number - 1),
        None,
    )
    return build_narrative_state_block(
        db, p, before_chapter=before, prev_volume=prev_vol,
    )
