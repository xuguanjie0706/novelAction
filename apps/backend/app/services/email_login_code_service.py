"""邮箱登录验证码服务。"""

from __future__ import annotations

import hashlib
import hmac
import random
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.config import settings
from app.models.email_login_code import EmailLoginCode


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _hash_code(email: str, code: str) -> str:
    payload = f"{email.lower().strip()}:{code}".encode("utf-8")
    key = settings.EMAIL_LOGIN_CODE_SALT.encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _send_email_code(email: str, code: str, expire_minutes: int) -> bool:
    if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        return False

    msg = EmailMessage()
    msg["Subject"] = "NovelAction 登录验证码"
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = email
    msg.set_content(
        f"你的登录验证码是：{code}\n"
        f"有效期：{expire_minutes} 分钟\n"
        "若非本人操作，请忽略本邮件。"
    )

    smtp_cls = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
    with smtp_cls(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        if not settings.SMTP_USE_SSL:
            server.starttls()
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
    return True


def create_and_send_login_code(db: Session, email: str) -> tuple[bool, int, str | None]:
    """创建并发送（或开发态回显）邮箱登录验证码。"""
    now = _now_utc()
    cooldown = timedelta(seconds=settings.EMAIL_LOGIN_CODE_COOLDOWN_SECONDS)

    latest = (
        db.query(EmailLoginCode)
        .filter(EmailLoginCode.email == email)
        .order_by(EmailLoginCode.created_at.desc())
        .first()
    )
    if latest and latest.created_at and latest.created_at > now - cooldown:
        wait_seconds = int((latest.created_at + cooldown - now).total_seconds())
        return False, max(wait_seconds, 1), None

    code = f"{random.randint(0, 999999):06d}"
    expire_minutes = settings.EMAIL_LOGIN_CODE_EXPIRE_MINUTES
    record = EmailLoginCode(
        email=email,
        code_hash=_hash_code(email, code),
        expires_at=now + timedelta(minutes=expire_minutes),
    )
    db.add(record)
    db.commit()

    sent = False
    try:
        sent = _send_email_code(email, code, expire_minutes)
    except Exception:
        sent = False

    if sent:
        return True, expire_minutes, None
    if settings.DEBUG:
        return True, expire_minutes, code
    return True, expire_minutes, None


def verify_login_code(db: Session, email: str, code: str) -> bool:
    """校验验证码并标记已使用。"""
    now = _now_utc()
    record = (
        db.query(EmailLoginCode)
        .filter(
            EmailLoginCode.email == email,
            EmailLoginCode.used_at.is_(None),
            EmailLoginCode.expires_at > now,
        )
        .order_by(EmailLoginCode.created_at.desc())
        .first()
    )
    if not record:
        return False

    expected = _hash_code(email, code)
    if not hmac.compare_digest(expected, record.code_hash):
        return False

    record.used_at = now
    db.add(record)
    db.commit()
    return True
