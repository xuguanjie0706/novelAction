"""大纲修订快照、质检留档与补丁应用。"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import OutlineNode, OutlineRevision
from app.routers.outline.helpers.expand_context import _outline_node_to_chapter_context

def _outline_snapshot_payload(nodes: list[OutlineNode]) -> dict:
    ordered = sorted(
        nodes,
        key=lambda node: (
            0 if node.parent_id is None else 1,
            node.sort_order or 0,
            str(node.id),
        ),
    )
    return {
        "schema_version": 1,
        "nodes": [
            {
                "id": str(node.id),
                "parent_id": str(node.parent_id) if node.parent_id else None,
                "node_type": node.node_type,
                "title": node.title,
                "summary": node.summary,
                "hook": node.hook,
                "highlight": node.highlight,
                "conflict": node.conflict,
                "sort_order": node.sort_order,
                "expected_words": node.expected_words,
                "reader_hook_score": node.reader_hook_score,
                "storyline_ids": node.storyline_ids or [],
                "involved_character_ids": node.involved_character_ids or [],
                "key_item_ids": node.key_item_ids or [],
                "key_skill_ids": node.key_skill_ids or [],
                "emotional_tone": node.emotional_tone,
                "pacing": node.pacing,
                "power_milestone": node.power_milestone,
                "foreshadows_laid": node.foreshadows_laid or [],
                "foreshadows_resolved": node.foreshadows_resolved or [],
                "extra": node.extra if isinstance(node.extra, dict) else {},
            }
            for node in ordered
        ],
    }


def _create_outline_revision(
    db: Session,
    *,
    project_id: str,
    label: str,
    source: str,
    scope: str = "book",
    volume_node_id: UUID | None = None,
    note: str | None = None,
    meta: dict[str, Any] | None = None,
) -> OutlineRevision:
    q = db.query(OutlineNode).filter(OutlineNode.project_id == project_id)
    if scope == "volume" and volume_node_id:
        direct_children = db.query(OutlineNode.id).filter(
            OutlineNode.project_id == project_id,
            OutlineNode.parent_id == volume_node_id,
        ).all()
        child_ids = [row[0] for row in direct_children]
        q = q.filter(
            (OutlineNode.id == volume_node_id)
            | (OutlineNode.parent_id == volume_node_id)
            | (OutlineNode.parent_id.in_(child_ids))
        )
    nodes = q.order_by(OutlineNode.sort_order, OutlineNode.created_at).all()
    snapshot = _outline_snapshot_payload(nodes)
    revision = OutlineRevision(
        project_id=project_id,
        label=label,
        source=source,
        scope=scope,
        volume_node_id=volume_node_id,
        note=note,
        snapshot=snapshot,
        meta=meta or {},
        node_count=len(snapshot["nodes"]),
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision


def _load_volume_chapter_context(
    db: Session,
    project_id: str,
    volume_node: OutlineNode,
) -> list[dict]:
    """
    Load chapter plans under a volume, including the legacy volume -> arc -> chapter_plan shape.
    """
    children = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.parent_id == volume_node.id,
    ).all()
    parent_ids = [volume_node.id, *[child.id for child in children if child.node_type == "arc"]]
    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
        OutlineNode.parent_id.in_(parent_ids),
    ).all()
    chapters = [_outline_node_to_chapter_context(node) for node in nodes]
    chapters.sort(key=lambda chapter: chapter.get("number") or 0)
    return chapters


def _chapter_number_value(chapter: dict) -> int:
    number = chapter.get("number")
    return number if isinstance(number, int) else 0


def _with_outline_quality(report_owner: OutlineNode, report: dict) -> dict:
    current_extra = report_owner.extra if isinstance(report_owner.extra, dict) else {}
    return {
        **current_extra,
        "outline_quality": report,
    }


def _create_quality_revision(
    db: Session,
    *,
    project_id: str,
    scope: str,
    report: dict[str, Any],
    volume_node: OutlineNode | None = None,
) -> OutlineRevision:
    if scope == "volume" and volume_node is not None:
        label = f"质检报告：{volume_node.title}"
        note = "单卷大纲质检自动留档"
        volume_node_id = volume_node.id
    else:
        label = "质检报告：全书大纲"
        note = "全书大纲质检自动留档"
        volume_node_id = None
    return _create_outline_revision(
        db,
        project_id=project_id,
        label=label,
        source="quality",
        scope="volume" if scope == "volume" else "book",
        volume_node_id=volume_node_id,
        note=note,
        meta={
            "quality_scope": scope,
            "quality_status": report.get("status"),
            "quality_score": report.get("overall_score"),
            "quality_report": report,
        },
    )


def _outline_node_plan_fields(node: OutlineNode) -> dict:
    extra = node.extra if isinstance(node.extra, dict) else {}
    return {
        "opening_hook": node.hook or "",
        "core_event": node.summary or "",
        "character_change": node.conflict or "",
        "foreshadow": extra.get("foreshadow", ""),
        "end_hook": extra.get("end_hook") or node.highlight or "",
    }


def _apply_outline_patch_to_node(node: OutlineNode, patch: dict) -> dict:
    before = _outline_node_plan_fields(node)
    fields = patch.get("fields") if isinstance(patch.get("fields"), dict) else patch
    extra = node.extra if isinstance(node.extra, dict) else {}
    next_extra = {**extra}

    opening_hook = fields.get("opening_hook")
    core_event = fields.get("core_event")
    character_change = fields.get("character_change")
    foreshadow = fields.get("foreshadow")
    end_hook = fields.get("end_hook")

    if isinstance(opening_hook, str) and opening_hook.strip():
        node.hook = opening_hook.strip()
    if isinstance(core_event, str) and core_event.strip():
        node.summary = core_event.strip()
    if isinstance(character_change, str) and character_change.strip():
        node.conflict = character_change.strip()
    if isinstance(foreshadow, str):
        next_extra["foreshadow"] = foreshadow.strip()
    if isinstance(end_hook, str) and end_hook.strip():
        node.highlight = end_hook.strip()
        next_extra["end_hook"] = end_hook.strip()

    node.extra = next_extra
    after = _outline_node_plan_fields(node)
    return {
        "chapter_number": patch.get("chapter_number"),
        "node_id": str(node.id) if node.id else None,
        "title": node.title,
        "before": before,
        "after": after,
        "reason": patch.get("reason", ""),
    }

