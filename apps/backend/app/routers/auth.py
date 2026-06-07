"""认证路由模块。

资源边界：仅处理 /api/v1/auth/* 路径，提供注册、登录、当前用户查询三个端点。
所有业务逻辑（密码哈希、JWT 生成/解码）委托给 app.utils.auth，不在此模块直接操作加密库。

端点列表：
    POST /auth/register   注册新账号，成功返回 access_token + user 信息
    POST /auth/login      账号密码登录，成功返回 access_token + user 信息
    GET  /auth/me         校验 token 并返回当前登录用户信息（需要 Bearer Token）
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import (
    SendRegisterCodeRequest,
    SendRegisterCodeResponse,
    TokenResponse,
    UserLoginRequest,
    UserOut,
    UserRegisterRequest,
)
from app.services.email_login_code_service import create_and_send_login_code, verify_login_code
from app.utils.auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _find_user_by_email(db: Session, email: str) -> User | None:
    normalized = _normalize_email(email)
    return db.query(User).filter(User.email == normalized).first()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: UserRegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """注册新账号。

    Args:
        body: 包含 email / password / username / email_code 的注册请求体。
        db: 数据库 session（由依赖注入提供）。

    Returns:
        TokenResponse：access_token + token_type + user 公开信息。

    Raises:
        HTTPException 400: 邮箱已被注册。
    """
    email = _normalize_email(body.email)
    if _find_user_by_email(db, email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被注册，请直接登录",
        )

    if not verify_login_code(db, email, body.email_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱验证码错误或已过期",
        )

    username = body.username or email.split("@")[0]
    user = User(
        email=email,
        username=username,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.flush()  # 获取 user.id，供积分初始化使用

    # 注册赠送积分（CREDIT_NEW_USER_BONUS > 0 时生效）
    from app.config import settings as _settings
    bonus = _settings.CREDIT_NEW_USER_BONUS
    if bonus > 0:
        from app.services import credit_service as _cs
        _cs.topup(
            user.id,
            bonus,
            ref_type="registration_bonus",
            note=f"新用户注册赠送 {bonus} 积分",
            db=db,
        )

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
    email = _normalize_email(body.email)
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    token = create_access_token(sub=str(user.id))
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/register/code/send", response_model=SendRegisterCodeResponse)
def send_register_code(body: SendRegisterCodeRequest, db: Session = Depends(get_db)) -> SendRegisterCodeResponse:
    """发送邮箱注册验证码。"""
    email = _normalize_email(body.email)
    if _find_user_by_email(db, email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被注册，请直接登录",
        )

    ok, expire_or_wait, dev_code = create_and_send_login_code(db, email)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"发送过于频繁，请 {expire_or_wait} 秒后重试",
        )

    return SendRegisterCodeResponse(expire_minutes=expire_or_wait, dev_code=dev_code)


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    """获取当前登录用户信息。

    需要在请求头携带：Authorization: Bearer <token>

    Returns:
        UserOut：当前用户公开信息（不含密码哈希）。
    """
    return UserOut.model_validate(current_user)
