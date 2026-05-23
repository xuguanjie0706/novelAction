"""
复盘 character_updates 的 character_id 解析。

AI 常返回 su_chen_id / protagonist_su_chen_id 等 slug，原逻辑仅接受 UUID 导致整段更新被静默丢弃。
"""
from __future__ import annotations

import re
from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Character


class _CharRef:
    """resolve 内部用的轻量人物视图（ORM 或 auto_debrief states 均可）。"""

    __slots__ = ("id", "name", "role", "alias")

    def __init__(self, id, name, role="supporting", alias=None):
        self.id = id
        self.name = name
        self.role = role or "supporting"
        self.alias = alias or []


def _as_char_ref(row: Character | dict) -> _CharRef:
    if isinstance(row, Character):
        return _CharRef(row.id, row.name, row.role, row.alias or [])
    return _CharRef(
        row.get("id"),
        row.get("name") or "",
        row.get("role") or "supporting",
        row.get("alias") or [],
    )


def _normalize_slug(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (raw or "").lower()).strip("_")


def _name_pinyin_slug(name: str) -> str:
    """中文名 → lin_ming 形式 slug；无 pypinyin 时返回空串。"""
    name = (name or "").strip()
    if not name:
        return ""
    try:
        from pypinyin import Style, lazy_pinyin

        parts = lazy_pinyin(name, style=Style.NORMAL)
        return "_".join(p for p in parts if p).lower()
    except Exception:
        return ""


def _slug_matches_character(slug: str, char: _CharRef) -> bool:
    slug = _normalize_slug(slug)
    if not slug:
        return False
    name = (char.name or "").strip()
    if name and name.lower() in slug:
        return True
    for alias in char.alias or []:
        a = (alias or "").strip()
        if a and a.lower() in slug:
            return True
    py_slug = _name_pinyin_slug(name)
    if py_slug and (slug == py_slug or slug.startswith(f"{py_slug}_") or py_slug in slug):
        return True
    for alias in char.alias or []:
        py_alias = _name_pinyin_slug(alias)
        if py_alias and (slug == py_alias or py_alias in slug):
            return True
    return False


def resolve_character_ref(
    rows: Iterable[Character | dict],
    character_id: str | None,
    character_name: str | None = None,
) -> _CharRef | None:
    """将 character_id / character_name 解析为人物引用（不写库）。"""
    refs = [_as_char_ref(r) for r in rows]
    if not refs:
        return None

    cid = (character_id or "").strip()
    cname = (character_name or "").strip()

    if cid:
        try:
            uid = UUID(cid)
            hit = next((c for c in refs if c.id == uid), None)
            if hit:
                return hit
        except (ValueError, TypeError, AttributeError):
            pass

    if cname:
        for c in refs:
            if c.name == cname:
                return c
            if cname in (c.alias or []):
                return c

    slug = _normalize_slug(cid)
    if slug:
        if "protagonist" in slug or slug.startswith("char_su") or "su_chen" in slug:
            prot = next((c for c in refs if c.role == "protagonist"), None)
            if prot:
                return prot
        for c in refs:
            if _slug_matches_character(slug, c):
                return c

    return None


def resolve_character_id_from_states(
    character_states: list[dict],
    character_id: str | None,
    character_name: str | None = None,
) -> str | None:
    """auto_debrief 解析后：把 slug character_id 替换为真实 UUID 字符串。"""
    ref = resolve_character_ref(character_states, character_id, character_name)
    return str(ref.id) if ref and ref.id else None


def resolve_character_updates_from_states(
    character_updates: list[dict],
    character_states: list[dict],
) -> list[dict]:
    """就地修正 auto_debrief 返回的 character_updates[].character_id。"""
    fixed: list[dict] = []
    for cu in character_updates:
        if not isinstance(cu, dict):
            continue
        row = dict(cu)
        resolved = resolve_character_id_from_states(
            character_states,
            row.get("character_id"),
            row.get("character_name"),
        )
        if resolved:
            row["character_id"] = resolved
            fixed.append(row)
    return fixed


def resolve_character_for_update(
    db: Session,
    project_id: str,
    character_id: str | None,
    character_name: str | None = None,
    *,
    characters: Iterable[Character] | None = None,
) -> Character | None:
    """
    将复盘 payload 中的 character_id（UUID 或 AI slug）解析为 Character ORM。

    解析顺序：合法 UUID → 姓名/别名精确匹配 → protagonist slug → 拼音 slug 模糊匹配。
    """
    rows = list(characters) if characters is not None else (
        db.query(Character).filter(Character.project_id == project_id).all()
    )
    ref = resolve_character_ref(rows, character_id, character_name)
    if not ref:
        return None
    return next((c for c in rows if isinstance(c, Character) and c.id == ref.id), None)
