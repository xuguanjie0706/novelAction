"""积分核心服务。

职责：
- Model Tier 判定：根据模型名称字符串匹配，确定计费档位（heavy / standard / light）。
- Token → 积分换算：按档位费率 + 向上取整，保证每次 AI 调用结果为正整数积分。
- 余额查询 / 预检：``get_balance``、``is_sufficient``。
- 扣费 / 充值 / 调账：``deduct``、``topup``、``admin_adjust``，所有写操作在同一事务内
  原子更新 ``user_credits.balance`` 并插入 ``credit_transactions`` 流水。
- 账户初始化：``get_or_create``，首次查询时自动建账（余额=0）。

费率表（每 1000 token）：

    档位       input   output   适用场景
    -------    -----   ------   --------------------
    heavy        5       15     GPT-4 / Claude Opus / Gemini Pro 等大模型
    standard     1        3     GPT-3.5 / Claude Sonnet/Haiku / Gemini Flash / Qwen-Plus 等
    light        0        0     本地模型（Ollama / LM Studio），免费使用

费率单位为「积分/千 token」，换算时向上取整，最低 1 积分/次（实际扣费结果 ≥ 1）。
当档位为 light 时成本=0，不产生流水记录，直接返回。

调用方约定：
- 所有写操作传入已开启事务的 ``db: Session``，由调用方 commit / rollback。
- 只读查询可传 ``db=None``，函数内部自行开关连接。

禁止事项：
- 不在本模块做 HTTP 响应（402 等），该逻辑由 router 层处理。
- 不在本模块做 JWT / 用户身份校验，由 dependencies 层保证。
"""

from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.user_credit import CreditTransaction, UserCredit

# ──────────────────────────────────────────────
# 费率配置
# ──────────────────────────────────────────────

# 每 1000 token 消耗的积分数（整数）
_RATES: Dict[str, Dict[str, int]] = {
    "heavy":    {"input": 5,  "output": 15},
    "standard": {"input": 1,  "output": 3},
    "light":    {"input": 0,  "output": 0},   # 本地模型免费
}

# 模型名前缀/关键词 → 档位映射；按 heavy → standard 顺序匹配，未命中归为 light
#
# ⚠️ 匹配策略说明：对于带版本号的模型（如 gemini-1.5-flash、gemini-3-flash），
# 简单子串匹配会因为版本号夹在中间而失效（"gemini-flash" ∉ "gemini-3-flash"）。
# Gemini 系列因此使用 _is_gemini_flash / _is_gemini_pro 辅助函数做双关键词组合匹配。
_HEAVY_KEYWORDS = [
    "gpt-4",
    "claude-3-opus", "claude-opus-4", "claude-opus",
    "o1", "o3",
]
_STANDARD_KEYWORDS = [
    "gpt-3.5",
    "claude-3-sonnet", "claude-3-haiku", "claude-sonnet", "claude-haiku",
    "qwen-max", "qwen-plus", "qwen-long",
    "deepseek-v3", "deepseek-r1", "deepseek-chat",
    "glm-4",
]


def _is_gemini_flash(lower: str) -> bool:
    """判断是否为 Gemini Flash 系列（standard 档位）。

    处理 gemini-1.5-flash / gemini-2.0-flash / gemini-3-flash 等带版本号的命名，
    这类名称中 "gemini-flash" 不是有效子串，需要拆分为双关键词判断。
    """
    return "gemini" in lower and "flash" in lower


def _is_gemini_pro(lower: str) -> bool:
    """判断是否为 Gemini Pro 系列（heavy 档位）。

    处理 gemini-1.5-pro / gemini-2.0-pro / gemini-3-pro 等带版本号的命名。
    注意：gemini-flash 也含 "pro" 前缀（如 gemini-pro-exp），用 flash 优先排除。
    """
    return "gemini" in lower and "pro" in lower and "flash" not in lower


# ──────────────────────────────────────────────
# 公共工具函数
# ──────────────────────────────────────────────

def get_model_tier(model_name: str) -> str:
    """根据模型名确定计费档位。

    按 heavy → standard → light 顺序匹配（不区分大小写）。
    Gemini 系列使用双关键词组合匹配以兼容带版本号命名（如 gemini-3-flash）。
    未命中任何关键词的视为 light（本地 / 自建模型，免费）。

    Args:
        model_name: 实际请求的模型标识符（如 ``"gpt-4o"``、``"qwen-plus"``）。

    Returns:
        ``"heavy"`` | ``"standard"`` | ``"light"``
    """
    lower = (model_name or "").lower()
    # Gemini 系列：使用双关键词组合匹配（兼容 gemini-1.5-flash / gemini-3-flash 等带版本号命名）
    if _is_gemini_pro(lower):
        return "heavy"
    if _is_gemini_flash(lower):
        return "standard"
    for kw in _HEAVY_KEYWORDS:
        if kw in lower:
            return "heavy"
    for kw in _STANDARD_KEYWORDS:
        if kw in lower:
            return "standard"
    return "light"


def compute_cost(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    tier_override: Optional[str] = None,
) -> int:
    """计算一次 AI 调用消耗的积分（向上取整，最低 0）。

    公式：``ceil((input_tokens * input_rate + output_tokens * output_rate) / 1000)``

    Args:
        model_name: 模型名，用于关键词猜测档位（``tier_override`` 为 None 时生效）。
        prompt_tokens: 输入 token 数（包含 system + user 消息）。
        completion_tokens: 输出 token 数。
        tier_override: 显式指定档位（heavy/standard/light）；由 ``LlmProvider.tier``
            DB 字段传入，优先级高于关键词猜测，用于支持任意自定义 API 网关和模型名。

    Returns:
        应扣积分数（≥ 0 的整数）；light 档位恒为 0。
    """
    if tier_override and tier_override in _RATES:
        tier = tier_override
    else:
        tier = get_model_tier(model_name)
    rates = _RATES[tier]
    raw = (prompt_tokens * rates["input"] + completion_tokens * rates["output"]) / 1000.0
    return int(math.ceil(raw))


# ──────────────────────────────────────────────
# 账户操作
# ──────────────────────────────────────────────

def get_or_create(user_id: UUID, db: Session) -> UserCredit:
    """获取用户积分账户，不存在则自动创建（余额=0）。

    Args:
        user_id: 用户 UUID。
        db: 已开启事务的数据库 Session。

    Returns:
        ``UserCredit`` ORM 实例（已 flush 到 db，未 commit）。
    """
    credit = db.query(UserCredit).filter(UserCredit.user_id == user_id).first()
    if credit is None:
        credit = UserCredit(user_id=user_id, balance=0, total_consumed=0, total_topped_up=0)
        db.add(credit)
        db.flush()
    return credit


def get_balance(user_id: UUID, *, db: Optional[Session] = None) -> int:
    """返回用户当前积分余额；账户不存在时返回 0。

    Args:
        user_id: 用户 UUID。
        db: 可选的已开启事务 Session；为 None 时自行开关连接。

    Returns:
        整数积分余额，账户不存在时为 0。
    """
    own = db is None
    db = db or SessionLocal()
    try:
        credit = db.query(UserCredit).filter(UserCredit.user_id == user_id).first()
        return credit.balance if credit else 0
    finally:
        if own:
            db.close()


def is_sufficient(user_id: UUID, cost: int, *, db: Optional[Session] = None) -> bool:
    """检查余额是否足以支付 cost 积分。

    Args:
        user_id: 用户 UUID。
        cost: 预计消耗积分数。
        db: 可选的已开启事务 Session。

    Returns:
        ``True`` 表示余额充足（或 cost ≤ 0）；``False`` 表示余额不足。
    """
    if cost <= 0:
        return True
    return get_balance(user_id, db=db) >= cost


def topup(
    user_id: UUID,
    amount: int,
    ref_type: str,
    *,
    ref_id: Optional[str] = None,
    note: Optional[str] = None,
    db: Session,
) -> CreditTransaction:
    """为用户增加积分（充值 / 赠送 / 管理员操作）。

    调用方需在函数返回后自行 commit。

    Args:
        user_id: 目标用户 UUID。
        amount: 增加的积分数，必须 > 0。
        ref_type: 来源类型（如 ``"registration_bonus"``、``"admin_topup"``）。
        ref_id: 可选的关联业务主键字符串。
        note: 可选的备注说明。
        db: 已开启事务的 Session，由调用方管理 commit/rollback。

    Returns:
        已 flush 的 ``CreditTransaction`` 实例。

    Raises:
        ValueError: amount ≤ 0 时抛出。
    """
    if amount <= 0:
        raise ValueError(f"topup amount must be > 0, got {amount}")

    credit = get_or_create(user_id, db)
    credit.balance += amount
    credit.total_topped_up += amount

    txn = CreditTransaction(
        user_id=user_id,
        delta=amount,
        balance_after=credit.balance,
        ref_type=ref_type,
        ref_id=ref_id,
        note=note,
    )
    db.add(txn)
    db.flush()
    return txn


def deduct(
    user_id: UUID,
    cost: int,
    *,
    model: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    task: Optional[str] = None,
    ref_id: Optional[str] = None,
    db: Session,
) -> Optional[CreditTransaction]:
    """从用户账户中扣除积分（AI 调用后自动调用）。

    若 cost ≤ 0（如 light 档位本地模型），跳过写库直接返回 None。
    不检查余额是否足够，调用方需在此之前自行预检（``is_sufficient``）。

    Args:
        user_id: 用户 UUID。
        cost: 扣除积分数，≤ 0 时直接返回 None。
        model: 本次 AI 调用的模型名。
        prompt_tokens: 输入 token 数。
        completion_tokens: 输出 token 数。
        task: 任务标识（来自 llm_task_profiles）。
        ref_id: 关联 ``llm_call_logs.id`` 字符串。
        db: 已开启事务的 Session，由调用方管理 commit/rollback。

    Returns:
        已 flush 的 ``CreditTransaction`` 实例；cost ≤ 0 时为 None。
    """
    if cost <= 0:
        return None

    credit = get_or_create(user_id, db)
    credit.balance = max(0, credit.balance - cost)  # 防止穿透为负
    credit.total_consumed += cost

    txn = CreditTransaction(
        user_id=user_id,
        delta=-cost,
        balance_after=credit.balance,
        ref_type="llm_call",
        ref_id=ref_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        task=task,
    )
    db.add(txn)
    db.flush()
    return txn


def admin_adjust(
    user_id: UUID,
    delta: int,
    *,
    note: Optional[str] = None,
    db: Session,
) -> CreditTransaction:
    """管理员手动调整用户积分（正=加分，负=扣分）。

    余额最低归零，不会产生负余额。

    Args:
        user_id: 目标用户 UUID。
        delta: 调整量，正为增加，负为减少。
        note: 管理员备注。
        db: 已开启事务的 Session，由调用方管理 commit/rollback。

    Returns:
        已 flush 的 ``CreditTransaction`` 实例。

    Raises:
        ValueError: delta == 0 时抛出。
    """
    if delta == 0:
        raise ValueError("admin_adjust delta must be non-zero")

    credit = get_or_create(user_id, db)
    credit.balance = max(0, credit.balance + delta)
    if delta > 0:
        credit.total_topped_up += delta
    else:
        credit.total_consumed += abs(delta)

    txn = CreditTransaction(
        user_id=user_id,
        delta=delta,
        balance_after=credit.balance,
        ref_type="admin_adjust",
        note=note,
    )
    db.add(txn)
    db.flush()
    return txn


# ──────────────────────────────────────────────
# 查询辅助
# ──────────────────────────────────────────────

def list_transactions(
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
    *,
    db: Optional[Session] = None,
) -> List[Dict[str, Any]]:
    """查询用户积分流水（按时间倒序）。

    Args:
        user_id: 用户 UUID。
        limit: 最多返回条数（上限 200）。
        offset: 分页偏移。
        db: 可选的已开启事务 Session；为 None 时自行开关连接。

    Returns:
        流水字典列表，每条含 id / delta / balance_after / ref_type / model /
        prompt_tokens / completion_tokens / task / note / created_at。
    """
    own = db is None
    db = db or SessionLocal()
    try:
        rows = (
            db.query(CreditTransaction)
            .filter(CreditTransaction.user_id == user_id)
            .order_by(CreditTransaction.created_at.desc())
            .offset(offset)
            .limit(max(1, min(limit, 200)))
            .all()
        )
        return [_txn_to_dict(r) for r in rows]
    finally:
        if own:
            db.close()


def list_all_user_credits(
    limit: int = 100,
    offset: int = 0,
    *,
    db: Optional[Session] = None,
) -> List[Dict[str, Any]]:
    """管理员：分页列出所有用户积分账户（按余额倒序）。

    Args:
        limit: 最多返回条数（上限 500）。
        offset: 分页偏移。
        db: 可选的已开启事务 Session。

    Returns:
        账户字典列表，每条含 user_id / balance / total_consumed / total_topped_up /
        created_at / updated_at。
    """
    own = db is None
    db = db or SessionLocal()
    try:
        rows = (
            db.query(UserCredit)
            .order_by(UserCredit.balance.desc())
            .offset(offset)
            .limit(max(1, min(limit, 500)))
            .all()
        )
        return [_credit_to_dict(r) for r in rows]
    finally:
        if own:
            db.close()


# ──────────────────────────────────────────────
# 内部序列化辅助
# ──────────────────────────────────────────────

def _credit_to_dict(row: UserCredit) -> Dict[str, Any]:
    return {
        "user_id": str(row.user_id),
        "balance": row.balance,
        "total_consumed": row.total_consumed,
        "total_topped_up": row.total_topped_up,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _txn_to_dict(row: CreditTransaction) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "delta": row.delta,
        "balance_after": row.balance_after,
        "ref_type": row.ref_type,
        "ref_id": row.ref_id,
        "model": row.model,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "task": row.task,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
