"""兑换码核心服务。

职责：
- 批量生成兑换码：``generate_batch``，返回新建的 RedeemCode 列表。
- 核销兑换码：``redeem``，校验码状态/有效期，原子写入积分并标记已核销。
- 列表查询：``list_codes``，管理员分页查询所有码（可按 batch_id / status 过滤）。
- 禁用单码：``disable``。

码格式：``XXXX-XXXX-XXXX-XXXX``（16 位大写字母数字 + 3 连字符），共 32 个字节（含连字符 19 字符）。
碰撞概率：16^16 ≈ 1.8×10^19，正常运营量不会冲突；生成时仍做唯一性重试保障。

调用方约定：
- 写操作传入已开启事务的 ``db: Session``，由调用方 commit / rollback。
- 只读查询可不传 db，函数内部自行开关连接。

错误码（ValueError message 约定，供 router 层解析成 HTTP 状态）：
- ``"CODE_NOT_FOUND"``   码不存在
- ``"CODE_DISABLED"``    码已被禁用
- ``"CODE_EXPIRED"``     码已过期
- ``"CODE_ALREADY_USED"``码已被使用
"""

from __future__ import annotations

import random
import string
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.redeem_code import RedeemCode
from app.services import credit_service

# ──────────────────────────────────────────────
# 码生成工具
# ──────────────────────────────────────────────

_CODE_CHARS = string.ascii_uppercase + string.digits  # A-Z0-9，36 个字符
_SEGMENT_LEN = 4
_SEGMENT_COUNT = 4


def _gen_raw_code() -> str:
    """生成一个 ``XXXX-XXXX-XXXX-XXXX`` 格式的随机码（无唯一性保证）。"""
    segments = [
        "".join(random.choices(_CODE_CHARS, k=_SEGMENT_LEN))
        for _ in range(_SEGMENT_COUNT)
    ]
    return "-".join(segments)


def _normalize_code_input(code_str: str) -> str:
    """将用户输入规范为库存中的 ``XXXX-XXXX-XXXX-XXXX`` 形式（大写）。

    支持：带/不带连字符、任意空格；仅当去分隔符后为 16 位合法字符时才重组，
    否则保留去除空格后的大写串（由查询决定是否命中）。
    """
    s = (code_str or "").strip().upper().replace(" ", "")
    compact = "".join(c for c in s if c in _CODE_CHARS)
    if len(compact) == _SEGMENT_LEN * _SEGMENT_COUNT:
        segments = [
            compact[i : i + _SEGMENT_LEN]
            for i in range(0, len(compact), _SEGMENT_LEN)
        ]
        return "-".join(segments)
    return s


def _unique_code(db: Session, max_retries: int = 10) -> str:
    """生成数据库内唯一的兑换码字符串。

    Args:
        db: 活跃的数据库 Session。
        max_retries: 最大重试次数（碰撞极低，通常 1 次即成功）。

    Returns:
        唯一码字符串。

    Raises:
        RuntimeError: 超过最大重试次数（实际业务中几乎不可能触发）。
    """
    for _ in range(max_retries):
        code = _gen_raw_code()
        exists = db.query(RedeemCode).filter(RedeemCode.code == code).first()
        if not exists:
            return code
    raise RuntimeError("兑换码生成冲突超过上限，请重试")


# ──────────────────────────────────────────────
# 写操作
# ──────────────────────────────────────────────

def generate_batch(
    count: int,
    credits: int,
    *,
    batch_id: Optional[str] = None,
    note: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    db: Session,
) -> List[RedeemCode]:
    """批量生成兑换码并写入数据库（调用方负责 commit）。

    Args:
        count: 生成数量（1-1000）。
        credits: 每张码的积分面值（> 0）。
        batch_id: 批次标识符（可选；未传时自动生成 UUID）。
        note: 管理员备注，如活动名称。
        expires_at: 过期时间（UTC）；为 None 表示永久有效。
        db: 活跃的数据库 Session。

    Returns:
        新建的 RedeemCode 对象列表（未 commit）。

    Raises:
        ValueError: count/credits 参数非法。
    """
    if count < 1 or count > 1000:
        raise ValueError("生成数量须在 1-1000 之间")
    if credits <= 0:
        raise ValueError("积分面值须大于 0")

    effective_batch_id = batch_id or str(uuid.uuid4())

    codes: List[RedeemCode] = []
    for _ in range(count):
        obj = RedeemCode(
            code=_unique_code(db),
            credits=credits,
            status="active",
            batch_id=effective_batch_id,
            note=note,
            expires_at=expires_at,
        )
        db.add(obj)
        codes.append(obj)

    return codes


def redeem(
    code_str: str,
    user_id: UUID,
    *,
    db: Session,
) -> Dict[str, Any]:
    """核销兑换码，将面值积分充入用户账户（调用方负责 commit）。

    Args:
        code_str: 兑换码字符串（大小写不敏感，连字符可选）。
        user_id: 核销用户 UUID。
        db: 活跃的数据库 Session。

    Returns:
        包含 ``code`` / ``credits`` / ``balance_after`` 的结果字典。

    Raises:
        ValueError: 码无效、已用、已过期或已禁用，message 为约定错误码常量。
    """
    normalized = _normalize_code_input(code_str)

    obj = db.query(RedeemCode).filter(RedeemCode.code == normalized).first()
    if not obj:
        raise ValueError("CODE_NOT_FOUND")

    if obj.status == "disabled":
        raise ValueError("CODE_DISABLED")

    if obj.status == "redeemed":
        raise ValueError("CODE_ALREADY_USED")

    # 检查有效期
    if obj.expires_at and obj.expires_at < datetime.now(timezone.utc):
        raise ValueError("CODE_EXPIRED")

    # 充值积分
    txn = credit_service.topup(
        user_id,
        int(obj.credits),
        ref_type="redeem_code",
        ref_id=str(obj.id),
        note=f"兑换码 {normalized}" + (f"（{obj.note}）" if obj.note else ""),
        db=db,
    )

    # 标记已核销
    obj.status = "redeemed"
    obj.redeemed_by = user_id
    obj.redeemed_at = datetime.now(timezone.utc)

    return {
        "code": normalized,
        "credits": int(obj.credits),
        "balance_after": txn.balance_after,
        "note": obj.note,
    }


def disable(code_id: UUID, *, db: Session) -> RedeemCode:
    """禁用指定兑换码（调用方负责 commit）。

    Args:
        code_id: 码的 UUID。
        db: 活跃的 Session。

    Returns:
        更新后的 RedeemCode 对象。

    Raises:
        ValueError: 码不存在或已核销（已核销的不可禁用）。
    """
    obj = db.query(RedeemCode).filter(RedeemCode.id == code_id).first()
    if not obj:
        raise ValueError("CODE_NOT_FOUND")
    if obj.status == "redeemed":
        raise ValueError("CODE_ALREADY_USED")
    obj.status = "disabled"
    return obj


# ──────────────────────────────────────────────
# 只读查询
# ──────────────────────────────────────────────

def list_codes(
    *,
    batch_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Optional[Session] = None,
) -> List[Dict[str, Any]]:
    """管理员：分页查询兑换码列表（按创建时间倒序）。

    Args:
        batch_id: 过滤批次（可选）。
        status: 过滤状态（active / redeemed / disabled；可选）。
        limit: 最多返回条数（1-500）。
        offset: 分页偏移。
        db: 可选 Session；为 None 时内部自行开关连接。

    Returns:
        码信息字典列表。
    """
    own = db is None
    db = db or SessionLocal()
    try:
        q = db.query(RedeemCode)
        if batch_id:
            q = q.filter(RedeemCode.batch_id == batch_id)
        if status:
            q = q.filter(RedeemCode.status == status)
        rows = (
            q.order_by(RedeemCode.created_at.desc())
            .offset(offset)
            .limit(max(1, min(limit, 500)))
            .all()
        )
        return [_to_dict(r) for r in rows]
    finally:
        if own:
            db.close()


def list_batches(*, db: Optional[Session] = None) -> List[Dict[str, Any]]:
    """管理员：聚合批次摘要（每批次的总数、已用数、面值）。

    Returns:
        批次摘要列表（按最新创建时间倒序）。
    """
    from sqlalchemy import func as sa_func

    own = db is None
    db = db or SessionLocal()
    try:
        rows = (
            db.query(
                RedeemCode.batch_id,
                RedeemCode.credits,
                RedeemCode.note,
                sa_func.count(RedeemCode.id).label("total"),
                sa_func.sum(
                    sa_func.cast(RedeemCode.status == "active", sa_func.Integer)
                ).label("active_count"),
                sa_func.sum(
                    sa_func.cast(RedeemCode.status == "redeemed", sa_func.Integer)
                ).label("redeemed_count"),
                sa_func.max(RedeemCode.created_at).label("created_at"),
                sa_func.min(RedeemCode.expires_at).label("expires_at"),
            )
            .group_by(RedeemCode.batch_id, RedeemCode.credits, RedeemCode.note)
            .order_by(sa_func.max(RedeemCode.created_at).desc())
            .all()
        )
        return [
            {
                "batch_id": r.batch_id,
                "credits": r.credits,
                "note": r.note,
                "total": r.total,
                "active_count": int(r.active_count or 0),
                "redeemed_count": int(r.redeemed_count or 0),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            }
            for r in rows
        ]
    finally:
        if own:
            db.close()


# ──────────────────────────────────────────────
# 序列化辅助
# ──────────────────────────────────────────────

def _to_dict(obj: RedeemCode) -> Dict[str, Any]:
    return {
        "id": str(obj.id),
        "code": obj.code,
        "credits": obj.credits,
        "status": obj.status,
        "batch_id": obj.batch_id,
        "note": obj.note,
        "redeemed_by": str(obj.redeemed_by) if obj.redeemed_by else None,
        "redeemed_at": obj.redeemed_at.isoformat() if obj.redeemed_at else None,
        "expires_at": obj.expires_at.isoformat() if obj.expires_at else None,
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
    }
