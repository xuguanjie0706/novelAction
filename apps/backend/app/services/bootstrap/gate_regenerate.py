"""
Bootstrap 闸门「重新生成」时的 DB 清理与再跑步骤。

仅在 LangGraph 对应闸门节点内调用；保证不留下孤儿 FK。
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Character, CharacterRelationship, OutlineNode, PowerSystem, Project


def wipe_power_systems(db: Session, project_id: UUID | str) -> None:
    """删除项目下全部境界体系（Step 2 闸门重跑前）。"""
    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    db.query(PowerSystem).filter(PowerSystem.project_id == pid).delete(synchronize_session=False)
    db.commit()


def wipe_characters(db: Session, project_id: UUID | str) -> None:
    """删除项目下人物与关系（Step 5 闸门重跑前）。"""
    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    ids = [r[0] for r in db.query(Character.id).filter(Character.project_id == pid).all()]
    if ids:
        db.query(CharacterRelationship).filter(
            or_(
                CharacterRelationship.from_character_id.in_(ids),
                CharacterRelationship.to_character_id.in_(ids),
            )
        ).delete(synchronize_session=False)
    db.query(Character).filter(Character.project_id == pid).delete(synchronize_session=False)
    db.commit()


def wipe_volume_nodes(db: Session, project_id: UUID | str) -> None:
    """删除项目下卷级 OutlineNode（Step 9 闸门重跑前；此时不应有 chapter_plan 子节点）。"""
    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
    db.query(OutlineNode).filter(
        OutlineNode.project_id == pid,
        OutlineNode.node_type == "volume",
    ).delete(synchronize_session=False)
    db.commit()


async def regenerate_power_systems(svc: Any, project: Project, ctx: dict) -> int:
    wipe_power_systems(svc.db, project.id)
    rows = await svc._gen_power_systems(project, ctx)
    return len(rows) if isinstance(rows, list) else (1 if rows else 0)


async def regenerate_characters(svc: Any, project: Project, ctx: dict) -> int:
    wipe_characters(svc.db, project.id)
    rows = await svc._gen_characters(project, ctx)
    if not isinstance(rows, list):
        rows = []
    ctx["_char_ids"] = [str(c.id) for c in rows]
    return len(rows)


async def regenerate_volumes(svc: Any, project: Project, ctx: dict) -> int:
    wipe_volume_nodes(svc.db, project.id)
    nodes = await svc._gen_volumes(project, ctx, inject_realm_fix_hint=True)
    if not isinstance(nodes, list):
        nodes = []
    ctx["_volume_ids"] = [str(n.id) for n in nodes]
    ctx["volumes_summary"] = " | ".join(
        f"{n.title}：{(n.summary or '')[:40]}" for n in nodes
    )
    return len(nodes)
