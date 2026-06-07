"""章纲伏笔引用解析。

OutlineNode.foreshadows_laid / foreshadows_resolved 的 ``id`` 字段在章纲生成时
常为伏笔 code 或中文名称（见 ``foreshadow_ops.ops_to_node_columns``），
不能当作 Foreshadow 表主键 UUID 直接查询。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Foreshadow
from app.services.ai.ingredient_types import ForeshadowOp


def is_uuid_string(val: object) -> bool:
    """判断字符串是否为合法 UUID。"""
    if val is None:
        return False
    try:
        UUID(str(val))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _coerce_foreshadow_ref(fw_ref: object) -> dict:
    """将章纲伏笔引用规范为 dict。"""
    if isinstance(fw_ref, dict):
        return fw_ref
    if isinstance(fw_ref, str) and fw_ref.strip():
        return {"id": fw_ref.strip(), "description": fw_ref.strip()}
    return {}


def lookup_foreshadow_by_ref(
    db: Session,
    project_id: str,
    fw_ref: object,
) -> Foreshadow | None:
    """按 UUID / title / code 解析 Foreshadow 行；无法匹配时返回 None。"""
    ref = _coerce_foreshadow_ref(fw_ref)
    raw_id = str(ref.get("id") or ref.get("foreshadow_id") or "").strip()
    desc = str(ref.get("description") or "").strip()

    if raw_id and is_uuid_string(raw_id):
        row = (
            db.query(Foreshadow)
            .filter(Foreshadow.id == raw_id, Foreshadow.project_id == project_id)
            .first()
        )
        if row:
            return row

    for needle in (raw_id, desc):
        if not needle:
            continue
        row = (
            db.query(Foreshadow)
            .filter(
                Foreshadow.project_id == project_id,
                Foreshadow.title == needle,
            )
            .first()
        )
        if row:
            return row
        if raw_id:
            row = (
                db.query(Foreshadow)
                .filter(
                    Foreshadow.project_id == project_id,
                    Foreshadow.code == raw_id,
                )
                .first()
            )
            if row:
                return row
    return None


def append_foreshadow_op_from_ref(
    ops: list[ForeshadowOp],
    seen_ids: set[str],
    *,
    fw_ref: object,
    op: str,
    db: Session,
    project_id: str,
    method_prefix: str,
) -> None:
    """从章纲伏笔引用追加一条 ForeshadowOp（兼容非 UUID id）。"""
    ref = _coerce_foreshadow_ref(fw_ref)
    raw_key = str(ref.get("id") or ref.get("foreshadow_id") or "").strip()
    desc = str(ref.get("description") or raw_key or "").strip()
    if not raw_key and not desc:
        return

    dedupe_key = raw_key or desc
    if dedupe_key in seen_ids:
        return

    fw = lookup_foreshadow_by_ref(db, project_id, fw_ref)
    if fw:
        fid = str(fw.id)
        if fid in seen_ids:
            return
        ops.append(ForeshadowOp(
            foreshadow_id=fid,
            title=fw.title or desc,
            op=op,
            priority=fw.priority or 3,
            laid_chapter=fw.laid_chapter_number if op == "resolve" else None,
            suggested_method=f"{method_prefix}{desc or fw.title or ''}",
        ))
        seen_ids.add(fid)
        seen_ids.add(dedupe_key)
        return

    ops.append(ForeshadowOp(
        foreshadow_id="",
        title=desc or raw_key,
        op=op,
        priority=3,
        laid_chapter=None,
        suggested_method=f"{method_prefix}{desc or raw_key}",
    ))
    seen_ids.add(dedupe_key)
