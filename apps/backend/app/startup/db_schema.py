"""启动期 schema 初始化：create_all + Alembic upgrade（与 main / restart / Docker 共用）。"""

from __future__ import annotations

from sqlalchemy.engine import Engine

from app.config import settings
from app.database import Base, engine
from app.startup.alembic_upgrade import ensure_alembic_at_head

# 注册 ORM 模型，供 create_all 使用
from app import models  # noqa: F401


def run_pre_start_schema(*, bind: Engine | None = None) -> str | None:
    """
    在 uvicorn 加载路由前执行。

    顺序：``create_all``（补全 ORM 表）→ ``alembic upgrade head``（补列/索引）。

    Returns:
        对齐后的 Alembic revision；若 ``ALEMBIC_UPGRADE_ON_STARTUP=false`` 则返回 ``None``。
    """
    eng = bind or engine
    Base.metadata.create_all(bind=eng)
    if not settings.ALEMBIC_UPGRADE_ON_STARTUP:
        return None
    return ensure_alembic_at_head(engine=eng)
