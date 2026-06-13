"""实验书架「情节档案」聚合 — 按章组合 计划/实际/线索/资产/关系，供回看视图。

把分散在 dabai_chapter_outlines（五拍计划）/ dabai_memories（复盘实际事实）/
dabai_clues（埋设·回收）/ dabai_assets（获得·消耗）/ dabai_relations（态度变化）
的产物，按章号聚合成一份「这一章实际写了什么」的档案。纯读，不产生新数据。

两个入口：
  - ``build_project_archive``：全书每章档案（左侧「档案」tab）。
  - ``build_chapter_archive``：单章档案（右侧栏随章卡）。
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiAsset, DabaiClue, DabaiMemory, DabaiRelation


def _plan_of(ch: DabaiChapterOutline) -> dict:
    """章纲五拍计划块。"""
    return {
        "shuang_type": ch.shuang_type or "",
        "yaqu_setup": ch.yaqu_setup or "",
        "emotion_turn": ch.emotion_turn or "",
        "yinbao": ch.yinbao or "",
        "shuang_payoff": ch.shuang_payoff or "",
        "end_hook": ch.end_hook or "",
        "location": ch.location or "",
        "realm_rank": ch.realm_rank,
        "is_big_beat": bool(ch.is_big_beat),
        "expected_words": ch.expected_words,
        "witnesses": list(ch.witnesses or []),
        "involved_characters": list(ch.involved_characters or []),
    }


def _mem_dict(m: DabaiMemory) -> dict:
    return {
        "id": str(m.id), "mem_type": m.mem_type, "content": m.content,
        "importance": m.importance, "tags": list(m.tags or []),
    }


def _assemble(
    ch: DabaiChapterOutline,
    mems: list[DabaiMemory],
    planted: list[DabaiClue],
    resolved: list[DabaiClue],
    asset_changes: list[dict],
    relation_changes: list[dict],
    first_appearances: list[str],
) -> dict:
    """组装单章档案（计划 + 实际 + 台账变更）。"""
    summary = next((m.content for m in mems if m.mem_type == "summary"), None)
    core = [_mem_dict(m) for m in mems if m.mem_type != "summary"]
    return {
        "chapter_id": str(ch.id),
        "chapter_number": ch.chapter_number,
        "title": ch.title or "",
        "status": ch.status or "planned",
        "word_count": len((ch.content or "")),
        "debriefed": bool(mems),
        "plan": _plan_of(ch),
        "summary": summary,
        "core_events": core,
        "clues_planted": [
            {"id": str(c.id), "title": c.title, "clue_type": c.clue_type,
             "description": c.description, "status": c.status}
            for c in planted
        ],
        "clues_resolved": [
            {"id": str(c.id), "title": c.title, "clue_type": c.clue_type}
            for c in resolved
        ],
        "asset_changes": asset_changes,
        "relation_changes": relation_changes,
        "first_appearances": first_appearances,
    }


def _asset_change_label(a: DabaiAsset, chapter: int) -> str | None:
    """该资产在本章发生的变更描述；无变更返回 None。"""
    if a.acquired_chapter == chapter:
        return "获得"
    if a.status_chapter == chapter and a.status in ("consumed", "lost"):
        return "消耗" if a.status == "consumed" else "失去"
    return None


def build_project_archive(db: Session, project: DabaiProject) -> list[dict]:
    """全书每章档案（章号升序）。批量取数，单遍聚合首次出场。"""
    chapters = (
        db.query(DabaiChapterOutline)
        .filter(DabaiChapterOutline.project_id == project.id)
        .order_by(DabaiChapterOutline.chapter_number)
        .all()
    )
    if not chapters:
        return []

    mems_by_ch: dict[int, list[DabaiMemory]] = defaultdict(list)
    for m in (
        db.query(DabaiMemory).filter(DabaiMemory.project_id == project.id)
        .order_by(DabaiMemory.importance.desc()).all()
    ):
        mems_by_ch[int(m.chapter_number or 0)].append(m)

    planted_by_ch: dict[int, list[DabaiClue]] = defaultdict(list)
    resolved_by_ch: dict[int, list[DabaiClue]] = defaultdict(list)
    for c in db.query(DabaiClue).filter(DabaiClue.project_id == project.id).all():
        if c.chapter_planted is not None:
            planted_by_ch[int(c.chapter_planted)].append(c)
        if c.chapter_resolved is not None:
            resolved_by_ch[int(c.chapter_resolved)].append(c)

    assets = db.query(DabaiAsset).filter(DabaiAsset.project_id == project.id).all()
    relations = db.query(DabaiRelation).filter(DabaiRelation.project_id == project.id).all()
    rel_by_ch: dict[int, list[dict]] = defaultdict(list)
    for r in relations:
        for h in (r.history or []):
            if not isinstance(h, dict) or h.get("chapter") is None:
                continue
            rel_by_ch[int(h["chapter"])].append({
                "from": r.from_name, "to": r.to_name,
                "attitude": h.get("attitude"), "reason": h.get("reason"),
            })

    seen_names: set[str] = set()
    out: list[dict] = []
    for ch in chapters:
        num = int(ch.chapter_number or 0)
        asset_changes = []
        for a in assets:
            label = _asset_change_label(a, num)
            if label:
                asset_changes.append({"name": a.name, "kind": a.kind, "change": label})
        # 首次出场：本章 involved/witnesses 中此前未出现过的人名
        stage = [str(n).strip() for n in
                 (list(ch.involved_characters or []) + list(ch.witnesses or [])) if str(n).strip()]
        firsts = []
        for n in stage:
            if n not in seen_names:
                seen_names.add(n)
                firsts.append(n)
        out.append(_assemble(
            ch, mems_by_ch.get(num, []), planted_by_ch.get(num, []),
            resolved_by_ch.get(num, []), asset_changes, rel_by_ch.get(num, []), firsts,
        ))
    return out


def build_chapter_archive(db: Session, project: DabaiProject, ch: DabaiChapterOutline) -> dict:
    """单章档案。首次出场通过查询更早章节的出场名集合判定。"""
    num = int(ch.chapter_number or 0)
    mems = (
        db.query(DabaiMemory)
        .filter(DabaiMemory.project_id == project.id, DabaiMemory.chapter_number == num)
        .order_by(DabaiMemory.importance.desc())
        .all()
    )
    planted = (
        db.query(DabaiClue)
        .filter(DabaiClue.project_id == project.id, DabaiClue.chapter_planted == num)
        .all()
    )
    resolved = (
        db.query(DabaiClue)
        .filter(DabaiClue.project_id == project.id, DabaiClue.chapter_resolved == num)
        .all()
    )
    asset_changes = []
    for a in db.query(DabaiAsset).filter(DabaiAsset.project_id == project.id).all():
        label = _asset_change_label(a, num)
        if label:
            asset_changes.append({"name": a.name, "kind": a.kind, "change": label})
    rel_changes = []
    for r in db.query(DabaiRelation).filter(DabaiRelation.project_id == project.id).all():
        for h in (r.history or []):
            if isinstance(h, dict) and h.get("chapter") == num:
                rel_changes.append({
                    "from": r.from_name, "to": r.to_name,
                    "attitude": h.get("attitude"), "reason": h.get("reason"),
                })

    stage = [str(n).strip() for n in
             (list(ch.involved_characters or []) + list(ch.witnesses or [])) if str(n).strip()]
    firsts: list[str] = []
    if stage:
        earlier = (
            db.query(DabaiChapterOutline.involved_characters, DabaiChapterOutline.witnesses)
            .filter(DabaiChapterOutline.project_id == project.id,
                    DabaiChapterOutline.chapter_number < num)
            .all()
        )
        prior: set[str] = set()
        for inv, wit in earlier:
            prior.update(str(n).strip() for n in (list(inv or []) + list(wit or [])))
        firsts = [n for n in dict.fromkeys(stage) if n not in prior]

    return _assemble(ch, mems, planted, resolved, asset_changes, rel_changes, firsts)
