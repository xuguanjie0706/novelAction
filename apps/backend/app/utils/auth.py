"""JWT 认证工具函数。

职责：密码哈希/验证、JWT access token 生成与解码。
所有加密操作集中于此，router 层只调用此处公共函数；密码使用 bcrypt 标准库式 API，避免 passlib 与新版本 bcrypt 不兼容。

使用方:
    from app.utils.auth import hash_password, verify_password, create_access_token, decode_access_token
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.config import settings

# JWT 算法与过期时长（分钟），从 settings 读取以便测试覆盖
_ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    """对明文密码做 bcrypt 哈希，返回哈希字符串。

    Args:
        plain: 用户提交的原始密码。

    Returns:
        bcrypt 哈希字符串，可安全落库。
    """
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码是否与哈希匹配。

    Args:
        plain: 用户提交的原始密码。
        hashed: 数据库中存储的哈希值。

    Returns:
        True 表示密码正确，False 表示不匹配。
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(sub: str, expires_minutes: Optional[int] = None) -> str:
    """生成 JWT access token。

    Args:
        sub: token subject，通常为 user_id（str 形式的 UUID）。
        expires_minutes: 过期时长（分钟），默认读 settings.ACCESS_TOKEN_EXPIRE_MINUTES。

    Returns:
        签名后的 JWT 字符串。
    """
    minutes = expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": sub, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """解码并验证 JWT，返回 sub（user_id）。

    Args:
        token: 来自 Authorization: Bearer <token> 的 JWT 字符串。

    Returns:
        token 中的 sub 字段（user_id），验签失败或过期时返回 None。
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[_ALGORITHM])
        sub: str = payload.get("sub")
        return sub if sub else None
    except JWTError:
        return None
