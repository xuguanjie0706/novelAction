"""卷叙述中的势力/归属疑似线索 — 仅供 consistency_scan AI 裁决。

后缀启发式（_extract_orgs）易将叙事短语误识别为组织名；此类线索不得直接写入
Project.extra.consistency_issues，由 Step 13 AI 结合全文语义确认或驳回。
"""

from __future__ import annotations

from typing import Any

from app.services.bootstrap.volume_entity_registry import (
    _extract_orgs,
    _org_matches_canonical,
    _protagonist_faction_from_ctx,
)


def _faction_names_from_ctx(db: Any, project_id: Any, ctx: dict) -> list[str]:
    from app.models import Faction

    names: list[str] = list(ctx.get("faction_names") or [])
    if names:
        return names
    return [
        f.name
        for f in db.query(Faction).filter(Faction.project_id == project_id).all()
        if f.name
    ]


def _scan_orphan_org_names(
    volumes: list[Any],
    faction_names: list[str],
) -> set[str]:
    orphan_orgs: set[str] = set()
    for vol in volumes:
        blob = " ".join(
            filter(None, [vol.title, vol.summary, vol.conflict, vol.hook])
        )
        for org in _extract_orgs(blob, faction_names):
            if not _org_matches_canonical(org, faction_names):
                orphan_orgs.add(org)
    return orphan_orgs


def collect_faction_semantic_hints(db: Any, project_id: Any, ctx: dict) -> list[str]:
    """收集势力/归属疑似线索（字符串列表），供 AI prompt 裁决，非最终 issue。"""
    from app.models import Character, OutlineNode

    hints: list[str] = []
    faction_names = _faction_names_from_ctx(db, project_id, ctx)
    if not faction_names:
        return hints

    volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order)
        .all()
    )
    if not volumes:
        return hints

    for org in sorted(_scan_orphan_org_names(volumes, faction_names)):
        hints.append(
            f"卷叙述正则疑似未登记组织「{org}」"
            f"（可能是档案别名、需补档新势力，或叙事短语误识别如「虚空之门」「守门人」）"
        )

    protagonist = (ctx.get("protagonist") or "").strip()
    if protagonist:
        protag_char = (
            db.query(Character)
            .filter(Character.project_id == project_id, Character.name == protagonist)
            .first()
        )
        protag_faction = (
            (protag_char.faction or "").strip() if protag_char
            else _protagonist_faction_from_ctx(ctx)
        )
        if protag_faction and "家" in protag_faction:
            surname = protagonist[0]
            if surname and surname not in protag_faction:
                hints.append(
                    f"主角「{protagonist}」姓{surname}与所属势力「{protag_faction}」姓氏不一致"
                    f"（若为养子/外姓传承则忽略）"
                )

    return hints
