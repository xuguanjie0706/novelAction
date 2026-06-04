"""
同人 Bootstrap 产物 → 标准表归一化。

复用番茄 converge 逻辑（卷导演单、境界表、开局承诺），并标记 bootstrap_mode=fanfic。
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import Character, CharacterRelationship, Project
from app.services.bootstrap.fanqie_normalize import (
    converge_fanqie_project,
    is_fanqie_project,
    sync_power_ladder_to_power_system,
)

# key_relationships 格式：A—关系—B（兼容 — / - / ～ / 、等分隔符）
_REL_SPLIT = re.compile(r"\s*[—–\-~～:：]\s*")


def is_fanfic_project(project: Project, ctx: dict | None = None) -> bool:
    ctx = ctx or {}
    extra = project.extra if isinstance(project.extra, dict) else {}
    if extra.get("fanfic_positioning"):
        return True
    pos = ctx.get("positioning") or extra.get("positioning") or {}
    return pos.get("bootstrap_mode") == "fanfic"


def is_tomato_pace_project(project: Project, ctx: dict | None = None) -> bool:
    """番茄章纲铁律：pace_type=fast 的原创番茄书 + 同人·番茄书。"""
    return is_fanqie_project(project, ctx) or is_fanfic_project(project, ctx)


def _persist_canon_relationships(db: Session, project: Project) -> int:
    """把 canon_pack.key_relationships 与 CP 落库为 CharacterRelationship（持久化优先硬规则）。"""
    extra = project.extra if isinstance(project.extra, dict) else {}
    canon = extra.get("fanfic_canon") or {}
    dev = extra.get("fanfic_deviation") or {}
    meta = extra.get("fanfic_meta") or {}

    chars = db.query(Character).filter(Character.project_id == project.id).all()
    by_name = {c.name: c for c in chars}
    if not by_name:
        return 0

    def _match(token: str) -> Character | None:
        token = (token or "").strip()
        if not token:
            return None
        if token in by_name:
            return by_name[token]
        # 宽松匹配：原著关系里可能带头衔/简称
        for name, c in by_name.items():
            if token in name or name in token:
                return c
        return None

    existing = {
        (r.from_character_id, r.to_character_id)
        for r in db.query(CharacterRelationship).filter(
            CharacterRelationship.project_id == project.id
        ).all()
    }
    created = 0

    def _add(a: Character, b: Character, rel_type: str, desc: str, intensity: int) -> None:
        nonlocal created
        if not a or not b or a.id == b.id:
            return
        if (a.id, b.id) in existing or (b.id, a.id) in existing:
            return
        db.add(CharacterRelationship(
            project_id=project.id,
            from_character_id=a.id,
            to_character_id=b.id,
            relation_type=(rel_type or "关联")[:50],
            description=(desc or "")[:500],
            intensity=intensity,
        ))
        existing.add((a.id, b.id))
        created += 1

    for raw in (canon.get("key_relationships") or [])[:12]:
        parts = [p for p in _REL_SPLIT.split(str(raw)) if p.strip()]
        if len(parts) < 3:
            continue
        a, rel, b = _match(parts[0]), parts[1].strip(), _match(parts[-1])
        _add(a, b, rel, str(raw), 5)

    # CP / 主视角感情线
    cp = (dev.get("cp_promise") or "").strip()
    focal = (meta.get("focal_characters") or "").strip()
    if cp and cp not in ("无", "none", "None") and focal:
        focal_parts = [p for p in _REL_SPLIT.split(focal) if p.strip()]
        if len(focal_parts) >= 2:
            _add(_match(focal_parts[0]), _match(focal_parts[1]), "感情线", cp, 8)

    if created:
        db.commit()
    return created


def converge_fanfic_project(db: Session, project: Project, ctx: dict | None = None) -> None:
    """同人线收敛：与番茄相同落库 + 标记 bootstrap_mode + 关系落库。"""
    ctx = dict(ctx or {})
    extra = dict(project.extra or {})
    extra["bootstrap_mode"] = "fanfic"
    project.extra = extra
    db.commit()
    sync_power_ladder_to_power_system(db, project)
    converge_fanqie_project(db, project, ctx)
    _persist_canon_relationships(db, project)
