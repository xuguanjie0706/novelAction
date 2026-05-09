"""共享 FastAPI 依赖：用户认证 + 项目所有权校验。

资源边界：
- get_current_user：从 Authorization: Bearer <token> 解析当前登录用户，未登录抛 401。
- verify_project_access：在路径含 ``{project_id}`` 的路由组上挂载，
  校验项目存在且归属当前用户，否则统一抛 404（避免泄露其他用户项目存在性）。

设计要点：
- 所有需要 user_id 隔离的项目子路由（characters / outline / chapters / ai 等）
  都通过在 ``include_router`` 时注入 ``dependencies=[Depends(verify_project_access)]``
  完成统一鉴权，路由实现内部不再各自重复 user_id 校验。
- 老数据 user_id IS NULL 的项目对所有已登录用户均不可见（按需通过 SQL 迁移）。
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.utils.auth import decode_access_token_full

# auto_error=False：自定义 401 文案，避免 FastAPI 默认 "Not authenticated"
_bearer = HTTPBearer(auto_error=False)


def is_admin_user(user: User | None) -> bool:
    """判定 user 是否为管理后台合成主体（role=admin token 注入）。"""
    return bool(getattr(user, "_is_admin", False))


def _build_admin_principal(sub: str) -> User:
    """构造合成 admin User（不入库），用于跨用户访问。

    仅设最少字段：id=None、is_active=True、username=sub、_is_admin=True。
    依赖此对象的代码必须先用 ``is_admin_user(...)`` 判定后再读取业务字段。
    """
    principal = User()
    principal.id = None  # 显式 None，提示禁止以 user_id 写库
    principal.email = f"admin:{sub}"
    principal.username = sub
    principal.is_active = True
    principal._is_admin = True  # type: ignore[attr-defined]
    return principal


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """从 Authorization: Bearer <token> 解析并返回当前主体。

    支持两类 token：
    - 普通用户 token（无 role 或 role=user）：返回 users 表中的 ORM 实例。
    - 管理员 token（role=admin）：返回合成 User（``_is_admin=True``，id=None），
      由 ``verify_project_access`` / 路由层按需放宽归属校验。

    Raises:
        HTTPException 401: token 缺失/无效/过期，或用户不存在/已停用。
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或 Token 已过期，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise unauthorized

    payload = decode_access_token_full(credentials.credentials)
    if not payload:
        raise unauthorized
    sub = payload.get("sub")
    if not sub:
        raise unauthorized

    role = payload.get("role")
    if role == "admin":
        # 管理后台 token：仅当 .env 仍配置了同名 ADMIN_USERNAME 时认可，
        # 防止下线管理员后旧 token 永久有效。
        if not settings.ADMIN_USERNAME or sub != settings.ADMIN_USERNAME:
            raise unauthorized
        return _build_admin_principal(sub)

    user = db.query(User).filter(User.id == sub, User.is_active == True).first()  # noqa: E712
    if not user:
        raise unauthorized
    return user


def verify_project_access(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project | None:
    """校验当前登录用户是否拥有路径中 ``project_id`` 指向的项目。

    适用范围：所有以 ``/projects/{project_id}/...`` 为前缀的子路由。
    通过在 ``include_router`` 时声明 ``dependencies=[Depends(verify_project_access)]``
    一次性挂载，子路由实现内部无需重复校验。

    实现说明：FastAPI 的 ``Path`` 参数不允许设默认值，故改为从 ``request.path_params``
    自取 ``project_id``；这样同一个依赖既可作用于 ``/projects/{project_id}/...``，
    也可作用于不含路径参的 ``/cover/image-providers`` 等同router 兄弟端点（仅做登录校验）。

    Args:
        request: 当前 Request；用于读取已解析的 path_params。
        current_user: 已登录用户（由 get_current_user 注入）。
        db: 数据库 Session。

    Returns:
        归属当前用户的 Project 实例；路径无 project_id 时返回 None。

    Raises:
        HTTPException 404: 项目不存在或不属于当前用户（统一 404 防探测）。
    """
    project_id = request.path_params.get("project_id")
    if not project_id:
        return None
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # 管理员 token：跨用户放行；普通用户：按 user_id 校验归属。
    if is_admin_user(current_user):
        return project
    if project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
