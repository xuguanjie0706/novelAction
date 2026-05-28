"""用户认证相关的 Pydantic schema。

职责：定义注册、登录请求体与响应体的数据结构；
与 ORM User 模型配合，保证字段名和类型契约在 router 层可读。
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


# ── 请求体 ───────────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    """注册请求体。

    Attributes:
        email: 邮箱地址，唯一，作为登录凭证。
        password: 明文密码，后端即刻哈希，原文不落库。
        username: 可选显示名，留空则回退到邮箱前缀。
        email_code: 邮箱验证码（6 位数字，一次性）。
    """

    email: EmailStr
    password: str
    username: Optional[str] = None
    email_code: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        """密码至少 6 位。"""
        if len(v) < 6:
            raise ValueError("密码不能少于 6 位")
        return v

    @field_validator("email_code")
    @classmethod
    def email_code_format(cls, v: str) -> str:
        code = v.strip()
        if len(code) != 6 or not code.isdigit():
            raise ValueError("邮箱验证码必须为 6 位数字")
        return code


class UserLoginRequest(BaseModel):
    """登录请求体。

    Attributes:
        email: 注册时使用的邮箱。
        password: 明文密码，仅用于比对，不存储。
    """

    email: EmailStr
    password: str


class SendRegisterCodeRequest(BaseModel):
    """发送注册验证码请求体。"""

    email: EmailStr


class SendRegisterCodeResponse(BaseModel):
    """发送注册验证码响应体。"""

    detail: str = "验证码已发送，请查收邮箱"
    expire_minutes: int
    dev_code: Optional[str] = None


# ── 响应体 ───────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    """用户公开信息（不含密码哈希）。"""

    id: UUID
    email: str
    username: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """登录/注册成功后返回的 token 响应。

    Attributes:
        access_token: JWT Bearer Token，客户端存 localStorage 后每次请求写入 Authorization 头。
        token_type: 固定为 "bearer"，供前端统一组装 header 用。
        user: 当前用户公开信息。
    """

    access_token: str
    token_type: str = "bearer"
    user: UserOut
