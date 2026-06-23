"""章节复盘资产快照：让整章重写可撤销 Item / Skill / Faction 的旧稿改动。"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from uuid import UUID

from app.models import Faction, Item, Skill

_MODELS = {"items": Item, "skills": Skill, "factions": Faction}
_SKIP_COLUMNS = {"project_id", "created_at", "updated_at"}


def _json_safe(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    return deepcopy(value)


def capture_project_asset_snapshot(db, project_id: str) -> dict:
    """捕获复盘前资产表业务字段；放入既有 undo JSON，无需新增表或 migration。"""
    payload: dict = {"snapshot_type": "assets"}
    for key, model in _MODELS.items():
        rows = db.query(model).filter(model.project_id == project_id).all()
        payload[key] = [
            {
                column.name: _json_safe(getattr(row, column.name))
                for column in model.__table__.columns
                if column.name not in _SKIP_COLUMNS
            }
            for row in rows
        ]
    return payload


def restore_project_asset_snapshot(db, project_id: str, snapshot: dict, chapter_id: str) -> None:
    """恢复复盘前资产字段，并删除明确由本章复盘新建的资产。"""
    for key, model in _MODELS.items():
        before_rows = [r for r in (snapshot.get(key) or []) if isinstance(r, dict) and r.get("id")]
        before_by_id = {str(r["id"]): r for r in before_rows}
        current_rows = db.query(model).filter(model.project_id == project_id).all()

        for row in current_rows:
            extra = row.extra if isinstance(row.extra, dict) else {}
            if str(extra.get("source_chapter_id") or "") == str(chapter_id):
                db.delete(row)
                continue
            state = before_by_id.get(str(row.id))
            if not state:
                continue
            for field, value in state.items():
                if field == "id":
                    continue
                setattr(row, field, deepcopy(value))
