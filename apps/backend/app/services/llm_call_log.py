from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.llm_call_log import LlmCallLog


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # 粗估：中英文混合场景按 4 字符 ≈ 1 token
    return max(1, (len(text) + 3) // 4)


def log_llm_call(
    *,
    mode: str,
    model: str,
    llm_endpoint: str,
    context: Dict[str, Any],
    duration_ms: int,
    status: str,
    prompt_text: str = "",
    completion_text: str = "",
    usage: Dict[str, Any] | None = None,
    error: str | None = None,
    input_payload: Any = None,
    output_payload: Any = None,
    db: Session | None = None,
) -> None:
    usage = usage or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")

    has_real_usage = isinstance(prompt_tokens, int) or isinstance(completion_tokens, int) or isinstance(total_tokens, int)
    if not isinstance(prompt_tokens, int):
        prompt_tokens = estimate_tokens(prompt_text)
    if not isinstance(completion_tokens, int):
        completion_tokens = estimate_tokens(completion_text)
    if not isinstance(total_tokens, int):
        total_tokens = prompt_tokens + completion_tokens

    own_db = db is None
    db = db or SessionLocal()
    try:
        row = LlmCallLog(
            mode=mode,
            model=model,
            llm_endpoint=llm_endpoint,
            status=status,
            duration_ms=duration_ms,
            context=context,
            token_usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "estimated": not has_real_usage,
            },
            error=error,
            input_payload=input_payload,
            output_payload=output_payload,
        )
        db.add(row)
        db.commit()
    finally:
        if own_db:
            db.close()


def _row_to_dict(row: LlmCallLog) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "mode": row.mode,
        "model": row.model,
        "llm_endpoint": row.llm_endpoint,
        "status": row.status,
        "duration_ms": row.duration_ms,
        "context": row.context or {},
        "token_usage": row.token_usage or {},
        "error": row.error,
        "input_payload": row.input_payload,
        "output_payload": row.output_payload,
    }


def list_llm_calls(limit: int = 200, db: Session | None = None) -> List[Dict[str, Any]]:
    own_db = db is None
    db = db or SessionLocal()
    try:
        rows = (
            db.query(LlmCallLog)
            .order_by(LlmCallLog.created_at.desc())
            .limit(max(1, min(limit, 2000)))
            .all()
        )
        return [_row_to_dict(r) for r in rows]
    finally:
        if own_db:
            db.close()


def clear_llm_calls(db: Session | None = None) -> int:
    own_db = db is None
    db = db or SessionLocal()
    try:
        deleted = db.query(LlmCallLog).delete()
        db.commit()
        return int(deleted or 0)
    finally:
        if own_db:
            db.close()
