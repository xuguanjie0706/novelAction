"""LLM 调用日志服务。

职责：
- ``log_llm_call``：落库每次 AI 调用记录，并在成功调用（status="ok"）且提供
  ``user_id`` 时，在同一事务内自动扣除积分（通过 credit_service）。
- ``list_llm_calls`` / ``clear_llm_calls``：管理后台查询与清理接口。

积分扣费规则：
- 仅 status="ok" 时扣费（失败调用不计费）。
- 使用 ``credit_service.compute_cost`` 按模型档位换算。
- light 档位（本地模型）cost=0，不产生流水记录。
- 扣费使用与日志落库相同的 db Session，保持原子性：日志与扣费要么都成功，
  要么都回滚，不会出现「日志有、积分没扣」或反向的情况。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.llm_call_log import LlmCallLog

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """粗估文本的 token 数（中英文混合，4 字符 ≈ 1 token）。"""
    if not text:
        return 0
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
    user_id: Optional[UUID] = None,
    task: Optional[str] = None,
    tier_override: Optional[str] = None,
    db: Session | None = None,
) -> str | None:
    """落库 LLM 调用日志，并在成功时原子扣除用户积分。

    Args:
        mode: 调用场景标识（来自 AIService.profile）。
        model: 实际请求的模型名。
        llm_endpoint: 请求 URL（已脱敏）。
        context: 业务上下文 JSON（project_id / task 等）。
        duration_ms: 请求耗时毫秒。
        status: ``"ok"`` 或 ``"error"``。
        prompt_text: 用于 token 估算的输入文本（有真实 usage 时仅作 fallback）。
        completion_text: 用于 token 估算的输出文本。
        usage: 模型返回的实际 token 统计字典（prompt_tokens / completion_tokens / total_tokens）。
        error: 失败时的错误消息。
        input_payload: 请求体摘要（可含完整消息列表）。
        output_payload: 响应摘要。
        user_id: 当前登录用户 UUID；提供时在 status="ok" 后自动扣费。
        task: 任务标识（写入积分流水的 task 字段）。
        tier_override: 强制指定计费档位（heavy/standard/light）；
            由 AIService._billing_tier 传入（来自 LlmProvider.tier DB 字段），
            优先级高于 credit_service 关键词猜测，支持任意自定义模型名。
        db: 已开启事务的 Session；为 None 时自行开关连接。

    Returns:
        落库的 ``LlmCallLog.id`` 字符串（用于积分流水的 ref_id）；异常时返回 None。
    """
    usage = usage or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")

    has_real_usage = (
        isinstance(prompt_tokens, int)
        or isinstance(completion_tokens, int)
        or isinstance(total_tokens, int)
    )
    if not isinstance(prompt_tokens, int):
        prompt_tokens = estimate_tokens(prompt_text)
    if not isinstance(completion_tokens, int):
        completion_tokens = estimate_tokens(completion_text)
    if not isinstance(total_tokens, int):
        total_tokens = prompt_tokens + completion_tokens

    own_db = db is None
    db = db or SessionLocal()
    log_id: str | None = None
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
        db.flush()  # 获取 row.id，供积分流水 ref_id 使用
        log_id = str(row.id)

        # ── 积分扣费（成功调用 + 已知 user_id 时）─────────────
        if status == "ok" and user_id is not None:
            try:
                from app.services import credit_service  # 延迟导入，避免循环依赖
                cost = credit_service.compute_cost(
                    model, prompt_tokens, completion_tokens,
                    tier_override=tier_override,
                )
                credit_service.deduct(
                    user_id,
                    cost,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    task=task,
                    ref_id=log_id,
                    db=db,
                )
            except Exception as credit_err:
                # 积分扣费失败不应阻断日志落库，仅记录警告
                logger.warning("积分扣费失败 user_id=%s: %s", user_id, credit_err)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if own_db:
            db.close()

    return log_id


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


def list_llm_calls(
    limit: int = 200,
    *,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    db: Session | None = None,
) -> List[Dict[str, Any]]:
    """分页查询 LLM 调用日志（管理后台使用）。"""
    own_db = db is None
    db = db or SessionLocal()
    try:
        q = db.query(LlmCallLog)
        if since is not None:
            q = q.filter(LlmCallLog.created_at >= since)
        if until is not None:
            q = q.filter(LlmCallLog.created_at <= until)
        rows = (
            q.order_by(LlmCallLog.created_at.desc())
            .limit(max(1, min(limit, 2000)))
            .all()
        )
        return [_row_to_dict(r) for r in rows]
    finally:
        if own_db:
            db.close()


def clear_llm_calls(db: Session | None = None) -> int:
    """清空所有调用日志（仅供开发 / 测试使用）。"""
    own_db = db is None
    db = db or SessionLocal()
    try:
        deleted = db.query(LlmCallLog).delete()
        db.commit()
        return int(deleted or 0)
    finally:
        if own_db:
            db.close()
