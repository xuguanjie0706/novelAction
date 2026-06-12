"""dabai 台账种子与存量修复（从 lab_ledger 拆出，避免上帝文件膨胀）。"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.dabai import DabaiProject
from app.models.dabai_lab import DabaiAsset, DabaiClue, DabaiRelation
from app.services.dabai.story_asset_debut import (
    plot_role_from_description,
    resolve_plot_asset_debut,
)

logger = logging.getLogger(__name__)

_ROLE_ATTITUDE = {
    "打脸对象": "敌对",
    "反派": "敌对",
    "女主": "暧昧",
    "导师": "扶持",
}

_GRADE_KEYWORDS = {
    "凡": 0, "下品": 0, "灵": 1, "中品": 1, "仙": 2, "上品": 2,
    "神": 3, "极品": 3, "传说": 4, "天外": 4,
}


def _protagonist_name(project: DabaiProject) -> str:
    for c in project.characters:
        if "主角" in (c.role or ""):
            return c.name
    return project.characters[0].name if project.characters else "主角"


def _guess_grade(name: str, description: str) -> int | None:
    text = (name or "") + (description or "")
    for kw, grade in _GRADE_KEYWORDS.items():
        if kw in text:
            return grade
    return None


def _golden_finger_asset_exists(db: Session, project_id) -> bool:
    return (
        db.query(DabaiAsset.id)
        .filter(DabaiAsset.project_id == project_id, DabaiAsset.kind == "golden_finger")
        .first()
        is not None
    )


def _seed_golden_finger_asset(
    db: Session, project: DabaiProject, protag: str,
) -> bool:
    """补种金手指台账（story_assets 先落库时不再整段跳过）。"""
    gf = project.golden_finger or {}
    if not gf.get("name") or _golden_finger_asset_exists(db, project.id):
        return False
    gf_name = str(gf["name"])[:120]
    gf_desc = str(gf.get("core_ability") or "")[:300]
    db.add(DabaiAsset(
        project_id=project.id, kind="golden_finger",
        name=gf_name, owner=protag,
        description=gf_desc,
        grade=_guess_grade(gf_name, gf_desc),
        cooldown_chapters=0,
        status="active", source="seed",
    ))
    return True


def _seed_character_relations(
    db: Session, project: DabaiProject, protag: str,
) -> bool:
    """从人物表派生关系种子（story_assets 已写 initial_relations 时跳过）。"""
    has_seed_rel = (
        db.query(DabaiRelation.id)
        .filter(DabaiRelation.project_id == project.id, DabaiRelation.source == "seed")
        .first()
    )
    if has_seed_rel:
        return False
    for c in project.characters:
        if c.name == protag:
            continue
        attitude = next(
            (v for k, v in _ROLE_ATTITUDE.items() if k in (c.role or "")), "中立",
        )
        db.add(DabaiRelation(
            project_id=project.id, from_name=protag, to_name=c.name,
            attitude=attitude, note=(c.function or "")[:200],
            last_change_chapter=0,
            history=[{"chapter": 0, "attitude": attitude, "reason": "开局设定"}],
            source="seed",
        ))
    return True


def reconcile_misseeded_protagonist_skills(
    db: Session, project: DabaiProject, protag: str,
) -> bool:
    """将误标 start 的主角功法从资产台账迁回线索（存量书修复，幂等）。"""
    rows = (
        db.query(DabaiAsset)
        .filter(
            DabaiAsset.project_id == project.id,
            DabaiAsset.kind == "skill",
            DabaiAsset.source == "seed",
            DabaiAsset.owner == protag,
            DabaiAsset.status == "active",
        )
        .all()
    )
    changed = False
    for a in rows:
        pseudo = {
            "kind": "skill",
            "plot_role": plot_role_from_description(a.description or ""),
            "owner": protag,
            "debut": "start",
        }
        if resolve_plot_asset_debut(pseudo, protag) != "later":
            continue
        clue_exists = (
            db.query(DabaiClue.id)
            .filter(DabaiClue.project_id == project.id, DabaiClue.title == a.name)
            .first()
        )
        if not clue_exists:
            desc = (a.description or "")[:300]
            db.add(DabaiClue(
                project_id=project.id, title=a.name, clue_type="foreshadow",
                description=f"{desc}（规划登场，自误种资产迁回）",
                chapter_planted=0, status="open", source="bootstrap",
            ))
        db.delete(a)
        changed = True
        logger.info(
            "dabai-lab 迁回误种主角功法 project=%s skill=%s", project.id, a.name,
        )
    return changed


def seed_ledgers(db: Session, project: DabaiProject) -> None:
    """开局台账派生（分项幂等）。失败静默，不阻塞调用方。"""
    try:
        protag = _protagonist_name(project)
        changed = (
            _seed_golden_finger_asset(db, project, protag)
            or _seed_character_relations(db, project, protag)
            or reconcile_misseeded_protagonist_skills(db, project, protag)
        )
        if changed:
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("dabai-lab 台账种子失败 project=%s: %s", project.id, exc)
        db.rollback()
