"""解析创作端「远程/Gemini」_profile 使用的连接信息。"""
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models.llm_provider import LlmProvider


def normalize_openai_base_url(url: str) -> str:
    """补全 OpenAI 兼容网关路径（例如根路径自动加 /v1）。"""
    u = url.strip().rstrip("/")
    if not u.endswith("/v1"):
        u = f"{u}/v1"
    return u


def pick_active_provider(db: Session) -> Optional[LlmProvider]:
    row = (
        db.query(LlmProvider)
        .filter(LlmProvider.enabled.is_(True), LlmProvider.is_default.is_(True))
        .first()
    )
    if row:
        return row
    return (
        db.query(LlmProvider)
        .filter(LlmProvider.enabled.is_(True))
        .order_by(LlmProvider.sort_order.asc(), LlmProvider.updated_at.desc())
        .first()
    )


def resolve_gemini_connection(db: Optional[Session]) -> Optional[Tuple[str, str, str]]:
    """
    返回 (base_url 原始, model_name, api_key 或空字符串)。
    优先级：数据库默认/启用的提供者 > 环境变量 GEMINI_*（兼容旧部署）。
    """
    if db is not None:
        row = pick_active_provider(db)
        if row:
            return (row.base_url, row.model_name, row.api_key or "")
    if settings.GEMINI_BASE_URL and settings.GEMINI_MODEL:
        return (
            settings.GEMINI_BASE_URL,
            settings.GEMINI_MODEL,
            settings.GEMINI_API_KEY or "",
        )
    return None


def seed_llm_from_env_if_empty() -> None:
    """首次启动且无记录时，用 .env 中 GEMINI_* 写入一条可编辑记录。"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        if db.query(LlmProvider).count() > 0:
            return
        if not (settings.GEMINI_BASE_URL and settings.GEMINI_MODEL):
            return
        p = LlmProvider(
            name="默认远程模型（自环境变量导入）",
            base_url=settings.GEMINI_BASE_URL.strip(),
            api_key=(settings.GEMINI_API_KEY or None),
            model_name=settings.GEMINI_MODEL.strip(),
            enabled=True,
            is_default=True,
            sort_order=0,
        )
        db.add(p)
        db.commit()
    finally:
        db.close()


def clear_other_defaults(db: Session, keep_id) -> None:
    for r in (
        db.query(LlmProvider)
        .filter(LlmProvider.id != keep_id, LlmProvider.is_default.is_(True))
        .all()
    ):
        r.is_default = False
