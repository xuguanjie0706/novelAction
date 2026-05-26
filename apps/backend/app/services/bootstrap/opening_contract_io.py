"""开局承诺（opening_contract）读写与 ReaderPromise 回退组装。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

BOOTSTRAP_OPENING_ORIGIN = "bootstrap_opening_contract"


def persist_opening_contract(svc: Any, project: Any, contract: dict) -> None:
    """写入 Project.extra.opening_contract（须新 dict + flag_modified 才可靠落库）。"""
    base = project.extra if isinstance(project.extra, dict) else {}
    project.extra = {**base, "opening_contract": contract}
    flag_modified(project, "extra")
    svc.db.commit()


def opening_contract_from_reader_promises(db: Session, project_id: str) -> dict:
    """Step 12 落库失败时，从已写入的 ReaderPromise 种子反推 opening_contract。"""
    from app.models import ReaderPromise

    rows = (
        db.query(ReaderPromise)
        .filter(ReaderPromise.project_id == project_id)
        .all()
    )
    out: dict[str, Any] = {}
    for rp in rows:
        extra = rp.extra if isinstance(rp.extra, dict) else {}
        if extra.get("origin") != BOOTSTRAP_OPENING_ORIGIN:
            continue
        key = extra.get("contract_key")
        text = (rp.promise_text or "").strip()
        if key and text:
            out[str(key)] = text
    return out


def _contract_field_count(contract: dict) -> int:
    n = 0
    for v in contract.values():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        if isinstance(v, (list, dict)) and not v:
            continue
        n += 1
    return n


def resolve_opening_contract(
    db: Session,
    project: Any,
    *,
    heal: bool = True,
) -> dict:
    """优先读 extra；为空时从 ReaderPromise 回退，并可写回 extra 自愈。"""
    extra = project.extra if isinstance(project.extra, dict) else {}
    oc = extra.get("opening_contract")
    if isinstance(oc, dict) and _contract_field_count(oc) > 0:
        return oc

    fallback = opening_contract_from_reader_promises(db, str(project.id))
    if not fallback:
        return {}

    if heal:
        try:
            base = project.extra if isinstance(project.extra, dict) else {}
            project.extra = {**base, "opening_contract": fallback}
            flag_modified(project, "extra")
            db.commit()
        except Exception:
            db.rollback()

    return fallback
