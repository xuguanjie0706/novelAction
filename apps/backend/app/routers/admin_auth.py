"""管理后台认证路由（与创作端用户体系完全隔离）。

资源边界：仅处理 /api/v1/admin/auth/* 路径。账号来源于环境变量
``ADMIN_USERNAME`` + ``ADMIN_PASSWORD``（明文配置），不写 users 表，
登录成功后签发 ``role=admin`` 的 JWT，供 apps/frontend 管理后台使用。

设计权衡：
- 单管理员场景，避免引入新表与权限矩阵；账号关闭只需清空环境变量。
- 与普通用户共用同一签名密钥与解码函数，但通过 ``role`` claim 严格区分；
  ``get_current_user`` 解码时仅当 sub 与现行 ADMIN_USERNAME 完全一致才认可，
  防止下线管理员后旧 token 永久有效。

端点列表：
    POST /admin/auth/login   管理员登录（用户名 + 密码）
    GET  /admin/auth/me      校验 token 是否仍为合法管理员
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.dependencies import get_current_user, is_admin_user
from app.models.user import User
from app.utils.auth import create_access_token

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


class AdminLoginRequest(BaseModel):
    """管理员登录请求体。"""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class AdminLoginResponse(BaseModel):
    """管理员登录响应。"""

    access_token: str
    token_type: str = "bearer"
    role: str = "admin"
    username: str


class AdminMeResponse(BaseModel):
    """`/admin/auth/me` 响应。"""

    role: str = "admin"
    username: str


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(body: AdminLoginRequest) -> AdminLoginResponse:
    """管理员登录。

    Args:
        body: 包含 username / password 的请求体。

    Returns:
        AdminLoginResponse：access_token + role + username。

    Raises:
        HTTPException 503: 服务端未配置 ADMIN_USERNAME/ADMIN_PASSWORD（默认关闭）。
        HTTPException 401: 凭据错误（统一返回同一错误消息防枚举）。
    """
    if not settings.ADMIN_USERNAME or not settings.ADMIN_PASSWORD:
        # 与普通 401 区分：明确告知运维管理后台入口未启用，避免误以为是密码错。
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="管理后台登录入口未启用：服务端未配置 ADMIN_USERNAME/ADMIN_PASSWORD",
        )

    # 简单常量比较即可（单管理员、明文配置）；如未来扩展为多管理员请改为哈希存储。
    if body.username != settings.ADMIN_USERNAME or body.password != settings.ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    token = create_access_token(sub=settings.ADMIN_USERNAME, role="admin")
    return AdminLoginResponse(
        access_token=token,
        username=settings.ADMIN_USERNAME,
    )


@router.get("/me", response_model=AdminMeResponse)
def admin_me(current_user: User = Depends(get_current_user)) -> AdminMeResponse:
    """校验当前 token 是否为合法管理员（用于前端启动时鉴权探活）。

    Raises:
        HTTPException 403: token 合法但 role != admin（普通用户 token 误用）。
    """
    if not is_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前 token 非管理员身份",
        )
    return AdminMeResponse(username=current_user.username or "")
