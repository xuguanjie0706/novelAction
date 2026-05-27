"""管理后台控制台聚合统计接口。

资源边界：仅需要 admin token，暴露系统级全局指标，不区分用户维度。

端点：
    GET /api/v1/admin/dashboard/stats   全量控制台指标（KPI + 趋势 + 活动流）

设计说明
--------
- 所有查询在单次请求内完成（多个独立 SQL），响应 < 1s 为设计目标。
- 时间边界统一以服务器 UTC 为准，前端按需折算时区。
- 近 7 天趋势按自然日分桶（DATE_TRUNC 无法移植时退化为 Python 分桶）。
- Token 消耗来源于 llm_call_logs.token_usage；字段可能缺失时用 COALESCE 兜底。
- 积分消耗来源于 credit_transactions（ref_type='llm_call'）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, is_admin_user
from app.models.user import User
from app.models.project import Project
from app.models.chapter import Chapter
from app.models.llm_call_log import LlmCallLog
from app.models.bootstrap_run import BootstrapRun
from app.models.rag_retrieval_log import RagRetrievalLog
from app.models.memory_conflict_detect_log import MemoryConflictDetectLog
from app.models.quality_debt import QualityDebt
from app.models.user_credit import CreditTransaction
from app.models import User as UserModel

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])

_UTC = timezone.utc


def _today_start() -> datetime:
    """今日 00:00:00 UTC。"""
    now = datetime.now(_UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _days_ago(n: int) -> datetime:
    """n 天前 00:00:00 UTC。"""
    return _today_start() - timedelta(days=n)


def _extract_token(log: Any, field: str) -> int:
    """安全提取 token_usage JSON 字段，不存在时返回 0。"""
    usage = getattr(log, "token_usage", None)
    if isinstance(usage, dict):
        return int(usage.get(field, 0) or 0)
    return 0


# ── 项目与内容统计 ────────────────────────────────────────────────────────

def _content_stats(db: Session) -> Dict[str, Any]:
    """小说数量（按状态）、章节总数、总字数。"""
    status_counts: Dict[str, int] = {}
    rows = (
        db.query(Project.status, sa_func.count(Project.id))
        .group_by(Project.status)
        .all()
    )
    total_projects = 0
    for status, cnt in rows:
        status_counts[status or "unknown"] = int(cnt)
        total_projects += int(cnt)

    chapter_agg = (
        db.query(
            sa_func.count(Chapter.id),
            sa_func.coalesce(sa_func.sum(Chapter.word_count), 0),
        )
        .filter(Chapter.deleted_at.is_(None))
        .one()
    )
    total_chapters = int(chapter_agg[0])
    total_words = int(chapter_agg[1])

    return {
        "total_projects": total_projects,
        "projects_by_status": status_counts,
        "total_chapters": total_chapters,
        "total_words": total_words,
    }


# ── 用户统计 ───────────────────────────────────────────────────────────────

def _user_stats(db: Session) -> Dict[str, Any]:
    """注册用户总数、活跃用户数。"""
    total = db.query(sa_func.count(UserModel.id)).scalar() or 0
    active = (
        db.query(sa_func.count(UserModel.id))
        .filter(UserModel.is_active.is_(True))
        .scalar()
        or 0
    )
    return {"total_users": int(total), "active_users": int(active)}


# ── Bootstrap 生成统计 ─────────────────────────────────────────────────────

def _bootstrap_stats(db: Session) -> Dict[str, Any]:
    """今日 / 总计 Bootstrap 运行数，按状态分布。"""
    today = _today_start()
    total = db.query(sa_func.count(BootstrapRun.id)).scalar() or 0
    today_total = (
        db.query(sa_func.count(BootstrapRun.id))
        .filter(BootstrapRun.created_at >= today)
        .scalar()
        or 0
    )
    status_rows = (
        db.query(BootstrapRun.status, sa_func.count(BootstrapRun.id))
        .group_by(BootstrapRun.status)
        .all()
    )
    by_status = {s: int(c) for s, c in status_rows}
    return {
        "bootstrap_total": int(total),
        "bootstrap_today": int(today_total),
        "bootstrap_by_status": by_status,
    }


# ── LLM 调用统计 ──────────────────────────────────────────────────────────

def _llm_stats(db: Session) -> Dict[str, Any]:
    """今日 & 总体 Token、调用量、成功率、平均耗时、上下文截断率。"""
    today = _today_start()

    # 全量聚合（今日）
    today_rows = (
        db.query(LlmCallLog)
        .filter(LlmCallLog.created_at >= today)
        .all()
    )
    total_today = len(today_rows)
    ok_today = sum(1 for r in today_rows if r.status == "ok")
    error_today = total_today - ok_today
    prompt_today = sum(_extract_token(r, "prompt_tokens") for r in today_rows)
    completion_today = sum(_extract_token(r, "completion_tokens") for r in today_rows)
    token_today = sum(_extract_token(r, "total_tokens") for r in today_rows)
    duration_today = [r.duration_ms for r in today_rows if r.duration_ms]
    avg_duration = int(sum(duration_today) / len(duration_today)) if duration_today else 0

    # 上下文截断 / 超限
    def _is_truncated(r: LlmCallLog) -> bool:
        ctx = r.context or {}
        return bool(
            ctx.get("context_truncated")
            or (isinstance(ctx.get("truncation_warnings"), list) and ctx["truncation_warnings"])
        )

    truncated_today = sum(1 for r in today_rows if _is_truncated(r))
    limit_exceeded_today = sum(
        1
        for r in today_rows
        if r.status == "error"
        and r.error
        and any(
            kw in r.error.lower()
            for kw in ("context length", "maximum context", "too many tokens", "上下文")
        )
    )

    # token_usage 为 JSON 列，跨库 SQL 聚合易出错；全量 token 用 Python 批量聚合。
    all_token_rows = db.query(LlmCallLog.token_usage, LlmCallLog.status).all()
    total_calls = len(all_token_rows)
    total_ok = sum(1 for _, s in all_token_rows if s == "ok")
    total_tokens_all = 0
    total_prompt_all = 0
    total_completion_all = 0
    for usage, _ in all_token_rows:
        if isinstance(usage, dict):
            total_tokens_all += int(usage.get("total_tokens", 0) or 0)
            total_prompt_all += int(usage.get("prompt_tokens", 0) or 0)
            total_completion_all += int(usage.get("completion_tokens", 0) or 0)

    success_rate = round(total_ok / total_calls * 100, 1) if total_calls else 0.0
    success_rate_today = round(ok_today / total_today * 100, 1) if total_today else 0.0

    # 任务类型 top-10 by token（需 context 中的 operation/task）
    op_rows = db.query(LlmCallLog.context, LlmCallLog.token_usage).all()
    task_token_map: Dict[str, int] = {}
    for ctx, usage in op_rows:
        if not isinstance(ctx, dict) or not isinstance(usage, dict):
            continue
        op = ctx.get("operation") or ctx.get("task") or "unknown"
        task_token_map[op] = task_token_map.get(op, 0) + int(usage.get("total_tokens", 0) or 0)
    top_tasks = sorted(task_token_map.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        # 今日
        "llm_calls_today": total_today,
        "llm_ok_today": ok_today,
        "llm_error_today": error_today,
        "token_today": token_today,
        "prompt_tokens_today": prompt_today,
        "completion_tokens_today": completion_today,
        "avg_duration_ms_today": avg_duration,
        "success_rate_today": success_rate_today,
        "truncated_today": truncated_today,
        "limit_exceeded_today": limit_exceeded_today,
        # 全量
        "llm_calls_total": total_calls,
        "success_rate_total": success_rate,
        "token_total": total_tokens_all,
        "prompt_tokens_total": total_prompt_all,
        "completion_tokens_total": total_completion_all,
        # 任务分布
        "top_tasks_by_token": [{"task": k, "tokens": v} for k, v in top_tasks],
    }


# ── 近 7 天 Token 趋势 ────────────────────────────────────────────────────

def _token_trend(db: Session) -> List[Dict[str, Any]]:
    """近 7 天（含今日）每日 token 消耗和调用量趋势。"""
    since = _days_ago(6)
    rows = (
        db.query(LlmCallLog.created_at, LlmCallLog.token_usage, LlmCallLog.status)
        .filter(LlmCallLog.created_at >= since)
        .all()
    )
    today = datetime.now(_UTC).date()
    buckets: Dict[str, Dict[str, int]] = {}
    for offset in range(6, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        buckets[day] = {"date": day, "tokens": 0, "calls": 0, "errors": 0}

    for created_at, usage, status in rows:
        if created_at is None:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=_UTC)
        day = created_at.astimezone(_UTC).date().isoformat()
        if day not in buckets:
            continue
        buckets[day]["calls"] += 1
        if status != "ok":
            buckets[day]["errors"] += 1
        if isinstance(usage, dict):
            buckets[day]["tokens"] += int(usage.get("total_tokens", 0) or 0)

    return list(buckets.values())


# ── RAG 检索统计 ──────────────────────────────────────────────────────────

def _rag_stats(db: Session) -> Dict[str, Any]:
    """RAG 检索状态分布、近 7 天平均耗时。"""
    today = _today_start()
    since7 = _days_ago(6)

    status_rows = (
        db.query(RagRetrievalLog.status, sa_func.count(RagRetrievalLog.id))
        .group_by(RagRetrievalLog.status)
        .all()
    )
    by_status = {s: int(c) for s, c in status_rows}
    total_rag = sum(by_status.values())
    semantic_ok = by_status.get("ok", 0)
    fallback = by_status.get("fallback_recency", 0)
    semantic_rate = round(semantic_ok / total_rag * 100, 1) if total_rag else 0.0

    avg_dur = (
        db.query(sa_func.avg(RagRetrievalLog.duration_ms))
        .filter(RagRetrievalLog.created_at >= since7)
        .scalar()
    )

    today_count = (
        db.query(sa_func.count(RagRetrievalLog.id))
        .filter(RagRetrievalLog.created_at >= today)
        .scalar()
        or 0
    )

    return {
        "rag_total": total_rag,
        "rag_semantic_ok": semantic_ok,
        "rag_fallback": fallback,
        "rag_semantic_rate": semantic_rate,
        "rag_avg_duration_ms": round(float(avg_dur), 1) if avg_dur else 0.0,
        "rag_today": int(today_count),
        "rag_by_status": by_status,
    }


# ── 记忆冲突 & 质检欠债 ───────────────────────────────────────────────────

def _quality_stats(db: Session) -> Dict[str, Any]:
    """记忆冲突检测次数 / 冲突总数；质检欠债分布。"""
    today = _today_start()

    conflict_today = (
        db.query(sa_func.count(MemoryConflictDetectLog.id))
        .filter(MemoryConflictDetectLog.created_at >= today)
        .scalar()
        or 0
    )
    total_conflicts_found = (
        db.query(sa_func.coalesce(sa_func.sum(MemoryConflictDetectLog.conflict_count), 0))
        .scalar()
        or 0
    )

    debt_rows = (
        db.query(QualityDebt.status, sa_func.count(QualityDebt.id))
        .group_by(QualityDebt.status)
        .all()
    )
    debt_by_status = {s: int(c) for s, c in debt_rows}
    pending_debts = debt_by_status.get("pending", 0)

    severity_rows = (
        db.query(QualityDebt.severity, sa_func.count(QualityDebt.id))
        .filter(QualityDebt.status == "pending")
        .group_by(QualityDebt.severity)
        .all()
    )
    debt_by_severity = {s: int(c) for s, c in severity_rows}

    return {
        "conflict_detections_today": int(conflict_today),
        "total_conflicts_found": int(total_conflicts_found),
        "quality_debt_pending": int(pending_debts),
        "quality_debt_by_status": debt_by_status,
        "quality_debt_by_severity": debt_by_severity,
    }


# ── 积分经济统计 ──────────────────────────────────────────────────────────

def _credit_stats(db: Session) -> Dict[str, Any]:
    """今日积分消耗、总消耗、总充值。"""
    today = _today_start()

    consumed_today = (
        db.query(sa_func.coalesce(sa_func.sum(sa_func.abs(CreditTransaction.delta)), 0))
        .filter(
            CreditTransaction.delta < 0,
            CreditTransaction.created_at >= today,
        )
        .scalar()
        or 0
    )
    topup_today = (
        db.query(sa_func.coalesce(sa_func.sum(CreditTransaction.delta), 0))
        .filter(
            CreditTransaction.delta > 0,
            CreditTransaction.ref_type.in_(["admin_topup", "redeem_code", "registration_bonus"]),
            CreditTransaction.created_at >= today,
        )
        .scalar()
        or 0
    )
    total_consumed = (
        db.query(sa_func.coalesce(sa_func.sum(sa_func.abs(CreditTransaction.delta)), 0))
        .filter(CreditTransaction.delta < 0)
        .scalar()
        or 0
    )
    total_topup = (
        db.query(sa_func.coalesce(sa_func.sum(CreditTransaction.delta), 0))
        .filter(
            CreditTransaction.delta > 0,
            CreditTransaction.ref_type.in_(["admin_topup", "redeem_code", "registration_bonus"]),
        )
        .scalar()
        or 0
    )

    return {
        "credits_consumed_today": int(consumed_today),
        "credits_topup_today": int(topup_today),
        "credits_consumed_total": int(total_consumed),
        "credits_topup_total": int(total_topup),
    }


# ── 最近活动流 ────────────────────────────────────────────────────────────

def _recent_activity(db: Session) -> Dict[str, Any]:
    """最近 Bootstrap 运行、最近 LLM 错误、最近记忆冲突事件。"""
    # 最近 10 次 Bootstrap 运行
    recent_boots = (
        db.query(BootstrapRun)
        .order_by(BootstrapRun.created_at.desc())
        .limit(10)
        .all()
    )
    boot_list = [
        {
            "id": str(b.id),
            "status": b.status,
            "logline": (b.logline or "")[:60],
            "mode": b.mode,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in recent_boots
    ]

    # 最近 10 条 LLM 错误
    recent_errors = (
        db.query(LlmCallLog)
        .filter(LlmCallLog.status != "ok")
        .order_by(LlmCallLog.created_at.desc())
        .limit(10)
        .all()
    )
    error_list = [
        {
            "id": str(r.id),
            "model": r.model,
            "error": (r.error or "")[:120],
            "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "context": {
                "operation": (r.context or {}).get("operation") or (r.context or {}).get("task"),
            },
        }
        for r in recent_errors
    ]

    # 最近 5 次记忆冲突检测（有冲突的）
    recent_conflicts = (
        db.query(MemoryConflictDetectLog)
        .filter(MemoryConflictDetectLog.conflict_count > 0)
        .order_by(MemoryConflictDetectLog.created_at.desc())
        .limit(5)
        .all()
    )
    conflict_list = [
        {
            "id": str(c.id),
            "project_id": str(c.project_id),
            "conflict_count": c.conflict_count,
            "trigger": c.trigger,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in recent_conflicts
    ]

    return {
        "recent_bootstraps": boot_list,
        "recent_llm_errors": error_list,
        "recent_memory_conflicts": conflict_list,
    }


# ── 路由 ──────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """控制台全量聚合指标。

    仅管理员可访问。

    Returns:
        dict，包含如下分组：
        - content: 小说 / 章节 / 字数统计
        - users: 用户数
        - bootstrap: Bootstrap 生成统计
        - llm: LLM 调用 Token / 成功率 / 耗时 / 任务分布
        - token_trend: 近 7 天 Token 趋势（列表，按日）
        - rag: RAG 检索状态分布与语义命中率
        - quality: 质检欠债与记忆冲突统计
        - credits: 积分经济数据
        - activity: 最近活动流（Bootstrap / 错误 / 冲突）
    """
    if not is_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前 token 非管理员身份",
        )
    return {
        "generated_at": datetime.now(_UTC).isoformat(),
        "content": _content_stats(db),
        "users": _user_stats(db),
        "bootstrap": _bootstrap_stats(db),
        "llm": _llm_stats(db),
        "token_trend": _token_trend(db),
        "rag": _rag_stats(db),
        "quality": _quality_stats(db),
        "credits": _credit_stats(db),
        "activity": _recent_activity(db),
    }
