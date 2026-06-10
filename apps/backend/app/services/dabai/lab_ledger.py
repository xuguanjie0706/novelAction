"""dabai 实验书架双台账 — 资产（功法/道具/金手指）+ 人物关系。

三个职责：
  1. seed：从 golden_finger / characters 派生开局台账（幂等，source=seed）；
  2. 注入：写章与导演单 prompt 的「当前台账」块（防能力/装备/关系漂移）；
  3. 维护：复盘提取的 asset_changes / relation_changes 落账（去重幂等）。

与精品文 Skill/Item/CharacterRelationship 完全隔离，不维护平行栈。
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiAsset, DabaiRelation

logger = logging.getLogger(__name__)

_ASSET_KINDS = {"skill", "item", "golden_finger"}
_KIND_LABELS = {"skill": "功法技能", "item": "道具法宝", "golden_finger": "金手指"}
_ROLE_ATTITUDE = {
    "打脸对象": "敌对",
    "反派": "敌对",
    "女主": "暧昧",
    "导师": "扶持",
}


def protagonist_name(project: DabaiProject) -> str:
    """主角名：role 含「主角」者优先，否则第一个人物，兜底「主角」。"""
    for c in project.characters:
        if "主角" in (c.role or ""):
            return c.name
    return project.characters[0].name if project.characters else "主角"


# ── 种子 ─────────────────────────────────────────────────────────────────────
def seed_ledgers(db: Session, project: DabaiProject) -> None:
    """开局台账派生（幂等：已有 seed 行则跳过）。失败静默，不阻塞调用方。"""
    try:
        has_seed = (
            db.query(DabaiAsset.id)
            .filter(DabaiAsset.project_id == project.id, DabaiAsset.source == "seed")
            .first()
            or db.query(DabaiRelation.id)
            .filter(DabaiRelation.project_id == project.id, DabaiRelation.source == "seed")
            .first()
        )
        if has_seed:
            return
        protag = protagonist_name(project)

        gf = project.golden_finger or {}
        if gf.get("name"):
            db.add(DabaiAsset(
                project_id=project.id, kind="golden_finger",
                name=str(gf["name"])[:120], owner=protag,
                description=str(gf.get("core_ability") or "")[:300],
                status="active", source="seed",
            ))

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
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("dabai-lab 台账种子失败 project=%s: %s", project.id, exc)
        db.rollback()


# ── 注入块 ───────────────────────────────────────────────────────────────────
def build_ledger_block(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline,
) -> str:
    """写章/导演单注入块：主角当前资产 + 在场人物关系 + 硬约束。空台账返回空串。"""
    protag = protagonist_name(project)
    lines: list[str] = []

    assets = (
        db.query(DabaiAsset)
        .filter(DabaiAsset.project_id == project.id, DabaiAsset.status == "active")
        .order_by(DabaiAsset.kind, DabaiAsset.acquired_chapter)
        .limit(20).all()
    )
    by_kind: dict[str, list[str]] = {}
    for a in assets:
        desc = f"（{(a.description or '')[:20]}）" if a.description else ""
        by_kind.setdefault(a.kind or "item", []).append(f"{a.name}{desc}")
    for kind in ("golden_finger", "skill", "item"):
        if by_kind.get(kind):
            lines.append(f"- {protag}的{_KIND_LABELS[kind]}：{'、'.join(by_kind[kind][:8])}")

    on_stage = {str(n) for n in (ch.witnesses or [])} | {
        str(n) for n in (ch.involved_characters or [])
    }
    rels = (
        db.query(DabaiRelation)
        .filter(DabaiRelation.project_id == project.id, DabaiRelation.from_name == protag)
        .all()
    )
    rel_lines = [
        f"{r.to_name}：{r.attitude or '中立'}"
        + (f"（第{r.last_change_chapter}章起）" if r.last_change_chapter else "")
        for r in rels if not on_stage or r.to_name in on_stage
    ]
    if rel_lines:
        lines.append(f"- 在场人物对{protag}的关系：{'；'.join(rel_lines[:10])}")

    if not lines:
        return ""
    lines.append(
        "- ★硬约束：禁止使用台账之外未获得的功法/法宝；已消耗/遗失的不得再用；"
        "人物态度须与台账一致，态度变化必须在正文交代原因。"
    )
    return "【当前台账（既定事实，不可违背）】\n" + "\n".join(lines)


# ── 复盘落账 ─────────────────────────────────────────────────────────────────
def _apply_asset_change(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline,
    item: dict, protag: str,
) -> str | None:
    action = str(item.get("action") or "").lower()
    name = str(item.get("name") or "").strip()[:120]
    if not name or action not in ("gain", "consume", "lose", "upgrade"):
        return None
    owner = str(item.get("owner") or protag).strip()[:100]
    note = str(item.get("note") or "")[:300]
    row = (
        db.query(DabaiAsset)
        .filter(DabaiAsset.project_id == project.id,
                DabaiAsset.name == name, DabaiAsset.owner == owner)
        .first()
    )
    if action == "gain":
        if row:
            if row.status != "active":  # 失而复得
                row.status, row.status_chapter = "active", ch.chapter_number
                return f"复得：{name}"
            return None  # 已持有，去重
        kind = str(item.get("kind") or "item").lower()
        db.add(DabaiAsset(
            project_id=project.id,
            kind=kind if kind in _ASSET_KINDS else "item",
            name=name, owner=owner, description=note,
            acquired_chapter=ch.chapter_number, status="active", source="debrief",
        ))
        return f"新获：{name}"
    if not row:
        return None
    if action == "upgrade":
        row.description = note or row.description
        row.status_chapter = ch.chapter_number
        return f"升级：{name}"
    row.status = "consumed" if action == "consume" else "lost"
    row.status_chapter = ch.chapter_number
    return f"{'消耗' if action == 'consume' else '遗失'}：{name}"


def _apply_relation_change(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline,
    item: dict, protag: str,
) -> str | None:
    to_name = str(item.get("to") or "").strip()[:100]
    attitude = str(item.get("attitude") or "").strip()[:40]
    if not to_name or not attitude:
        return None
    from_name = str(item.get("from") or protag).strip()[:100]
    reason = str(item.get("reason") or "")[:120]
    row = (
        db.query(DabaiRelation)
        .filter(DabaiRelation.project_id == project.id,
                DabaiRelation.from_name == from_name,
                DabaiRelation.to_name == to_name)
        .first()
    )
    entry = {"chapter": ch.chapter_number, "attitude": attitude, "reason": reason}
    if row:
        if row.attitude == attitude and row.last_change_chapter == ch.chapter_number:
            return None  # 同章重跑去重
        history = list(row.history or [])
        # 同章重跑但态度修正：替换该章旧记录
        history = [h for h in history if h.get("chapter") != ch.chapter_number]
        history.append(entry)
        old = row.attitude or "中立"
        row.attitude, row.history = attitude, history
        row.last_change_chapter = ch.chapter_number
        return f"{to_name}：{old}→{attitude}"
    db.add(DabaiRelation(
        project_id=project.id, from_name=from_name, to_name=to_name,
        attitude=attitude, note=reason, last_change_chapter=ch.chapter_number,
        history=[entry], source="debrief",
    ))
    return f"{to_name}：新增（{attitude}）"


def apply_ledger_changes(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline, result: dict,
) -> tuple[list[str], list[str]]:
    """复盘结果中的台账变更落库；返回 (资产变更摘要, 关系变更摘要)。不 commit。"""
    protag = protagonist_name(project)
    asset_logs: list[str] = []
    for item in list(result.get("asset_changes") or [])[:8]:
        if isinstance(item, dict):
            log = _apply_asset_change(db, project, ch, item, protag)
            if log:
                asset_logs.append(log)
    relation_logs: list[str] = []
    for item in list(result.get("relation_changes") or [])[:8]:
        if isinstance(item, dict):
            log = _apply_relation_change(db, project, ch, item, protag)
            if log:
                relation_logs.append(log)
    return asset_logs, relation_logs
