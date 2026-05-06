"""认证路由模块。

资源边界：仅处理 /api/v1/auth/* 路径，提供注册、登录、当前用户查询三个端点。
所有业务逻辑（密码哈希、JWT 生成/解码）委托给 app.utils.auth，不在此模块直接操作加密库。

端点列表：
    POST /auth/register   注册新账号，成功返回 access_token + user 信息
    POST /auth/login      账号密码登录，成功返回 access_token + user 信息
    GET  /auth/me         校验 token 并返回当前登录用户信息（需要 Bearer Token）
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserRegisterRequest, UserLoginRequest, TokenResponse, UserOut
from app.utils.auth import hash_password, verify_password, create_access_token, decode_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

# FastAPI 内置的 Bearer token 解析器；auto_error=False 让我们自定义 401 消息
_bearer = HTTPBearer(auto_error=False)


def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """依赖注入：从 Authorization: Bearer <token> 解析当前登录用户。

    Args:
        credentials: FastAPI 从请求头提取的 Bearer token；未携带时为 None。
        db: 数据库 session。

    Returns:
        对应的 User ORM 实例。

    Raises:
        HTTPException 401: token 缺失、无效或用户不存在/已停用。
    """
    _unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或 Token 已过期，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise _unauthorized

    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise _unauthorized

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise _unauthorized

    return user


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: UserRegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """注册新账号。

    Args:
        body: 包含 email / password / username 的注册请求体。
        db: 数据库 session（由依赖注入提供）。

    Returns:
        TokenResponse：access_token + token_type + user 公开信息。

    Raises:
        HTTPException 400: 邮箱已被注册。
    """
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被注册",
        )

    username = body.username or body.email.split("@")[0]
    user = User(
        email=body.email,
        username=username,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(sub=str(user.id))
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(body: UserLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """账号密码登录。

    Args:
        body: 包含 email / password 的登录请求体。
        db: 数据库 session。

    Returns:
        TokenResponse：access_token + token_type + user 公开信息。

    Raises:
        HTTPException 401: 邮箱不存在或密码错误（统一返回同一错误消息，防枚举）。
    """
    user = db.query(User).filter(User.email == body.email, User.is_active == True).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    token = create_access_token(sub=str(user.id))
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(_get_current_user)) -> UserOut:
    """获取当前登录用户信息。

    需要在请求头携带：Authorization: Bearer <token>

    Returns:
        UserOut：当前用户公开信息（不含密码哈希）。
    """
    return UserOut.model_validate(current_user)
